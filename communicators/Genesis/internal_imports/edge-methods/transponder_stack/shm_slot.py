#!/usr/bin/env python3
"""Shared-memory connection-slot prototype.

One communicator token per endpoint. One shared JSON bin on /dev/shm.
The bin is a two-way street: one queue-array lane per token. Sending is a
file write; the peer is woken by inotify and drains its own lane.

Terminal A:
  python shm_slot.py --name FOX   --listen a1b2c3d4e5f60718293a4b5c6d --peer 0dd3e7e0112233445566778899

Terminal B:
  python shm_slot.py --name OTTER --listen 0dd3e7e0112233445566778899 --peer a1b2c3d4e5f60718293a4b5c6d

`--listen` is this endpoint's token. `--peer` is the other endpoint's token.
The bin path is derived from the sorted pair so both processes open the same file.

Type a line and press enter to send. Ctrl-C to quit.

Non-interactive proof:
  python shm_slot.py --name FOX   --listen <tokA> --peer <tokB> --auto --hold 4
  python shm_slot.py --name OTTER --listen <tokB> --peer <tokA> --auto --hold 4

Wire framing: JSON objects in the lane queues. encode at send, decode at recv.
No sockets.

Capability row (harvest later for L1):
  listen yes | accept n/a | connect n/a | send yes | recv yes | close yes
  serve yes | request_response yes | send_and_close yes | persistent_client yes
"""


class DirWatch:
    IN_MODIFY = 0x00000002
    IN_CLOSE_WRITE = 0x00000008
    IN_MOVED_TO = 0x00000080
    IN_CREATE = 0x00000100
    IN_ATTRIB = 0x00000004
    WATCH_MASK = IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE | IN_ATTRIB
    EVENT_HDR = struct.Struct("iIII")
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.inotify_init.restype = ctypes.c_int
    libc.inotify_add_watch.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]

    @internalmethod
    def __init__(self, directory: str, filename: str):
        self.directory = directory
        self.filename = filename
        self.fd = DirWatch.libc.inotify_init()
        if self.fd < 0:
            raise OSError("inotify_init failed")
        wd = DirWatch.libc.inotify_add_watch(
            self.fd, directory.encode("utf-8"), DirWatch.WATCH_MASK
        )
        if wd < 0:
            os.close(self.fd)
            raise OSError("inotify_add_watch failed")

    @externalmethod
    def wait(self, timeout: float) -> bool:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return False
        data = os.read(self.fd, 4096)
        hit = False
        off = 0
        hdr = DirWatch.EVENT_HDR
        while off + hdr.size <= len(data):
            _wd, _mask, _cookie, namelen = hdr.unpack_from(data, off)
            off += hdr.size
            name = data[off:off + namelen].split(b"\x00", 1)[0].decode("utf-8", "replace")
            off += namelen
            if name == self.filename or name == "":
                hit = True
        return hit

    @externalmethod
    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class ShmSlot:
    @internalmethod
    def __init__(self, name: str, mine: str, peer: str):
        self.name = name
        self.mine = mine
        self.peer = peer
        self.bin_path, self.lock_path = Transponder_Locators.shm_bin_paths(mine, peer)
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.inbox = []
        self.inbox_lock = threading.Lock()
        self.replies = {}
        self.reply_events = {}
        self.alive = threading.Event()
        self.peer_up = threading.Event()
        self.watch = None
        self.watch_thread = None
        self.on_payload = None

    @dualmethod
    def addr_s(self) -> str:
        return f"shm://{os.path.basename(self.bin_path)}"

    @dualmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @internalmethod
    def _lock(self):
        os.makedirs(Transponder_Locators.BIN_DIR, exist_ok=True)
        lockf = open(self.lock_path, "a+")
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        return lockf

    @internalmethod
    def _read_bin(self) -> dict:
        try:
            with open(self.bin_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = ""
        if not raw.strip():
            return {"lanes": {self.mine: [], self.peer: []}, "present": {}}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            obj = {"lanes": {self.mine: [], self.peer: []}, "present": {}}
        obj.setdefault("lanes", {})
        obj["lanes"].setdefault(self.mine, [])
        obj["lanes"].setdefault(self.peer, [])
        obj.setdefault("present", {})
        return obj

    @internalmethod
    def _write_bin(self, obj: dict) -> None:
        tmp = self.bin_path + ".tmp"
        data = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.bin_path)

    @internalmethod
    def _mutate(self, fn):
        lockf = self._lock()
        try:
            obj = self._read_bin()
            result = fn(obj)
            self._write_bin(obj)
            return result
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
            lockf.close()

    @dualmethod
    def ensure_bin(self) -> None:
        def mark(obj):
            obj["present"][self.mine] = {"name": self.name, "ts": time.time()}
            return obj["present"]

        present = self._mutate(mark)
        print(f"[{self.name} BIN] {self.bin_path} present={list(present)}", flush=True)
        if self.peer in present:
            self.peer_up.set()

    @dualmethod
    def attach(self, wait: float) -> None:
        self.ensure_bin()
        self.watch = DirWatch(Transponder_Locators.BIN_DIR, os.path.basename(self.bin_path))
        self.alive.set()
        self.watch_thread = threading.Thread(
            target=self._watch_loop, name=f"{self.name}-inotify", daemon=True
        )
        self.watch_thread.start()
        print(f"[{self.name} LISTEN] token={self.mine} peer={self.peer}", flush=True)

        deadline = time.time() + wait
        while time.time() < deadline and not self.peer_up.is_set():
            self._drain()
            if self.peer_up.is_set():
                break
            remaining = max(0.05, deadline - time.time())
            self.watch.wait(timeout=min(0.5, remaining))
        if not self.peer_up.is_set():
            raise TimeoutError(f"{self.name} never saw peer token {self.peer} in {self.bin_path}")

    @externalmethod
    def wait_for_peer(self, timeout: float = 20.0) -> None:
        if not self.peer_up.is_set():
            self.attach(timeout)
        print(f"[{self.name} PEER UP] addr={self.addr_s()}", flush=True)

    @internalmethod
    def _watch_loop(self) -> None:
        while self.alive.is_set():
            try:
                hit = self.watch.wait(timeout=0.5)
            except Exception:
                if not self.alive.is_set():
                    break
                raise
            if self.alive.is_set() and (hit or not self.peer_up.is_set()):
                self._drain()

    @internalmethod
    def _drain(self) -> None:
        lockf = None
        items = []
        try:
            lockf = self._lock()
            obj = self._read_bin()
            if self.peer in obj.get("present", {}):
                self.peer_up.set()
            items = list(obj["lanes"].get(self.mine) or [])
            if items:
                obj["lanes"][self.mine] = []
                self._write_bin(obj)
        except Exception as e:
            print(f"[{self.name} DRAIN FAIL] {type(e).__name__}: {e}", flush=True)
            items = []
        finally:
            if lockf is not None:
                try:
                    fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
                    lockf.close()
                except Exception:
                    pass
        for raw in items:
            try:
                incoming = Transponder_Codec.decode_msg(raw)
            except Exception as e:
                print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                continue
            self._handle_incoming(incoming)

    @internalmethod
    def _handle_incoming(self, incoming: dict) -> None:
        cb = getattr(self, "on_payload", None)
        if cb is not None and incoming.get("kind") not in ("reply", "hello"):
            try:
                cb(incoming)
            except Exception as e:
                print(f"[{self.name} HOOK FAIL] {e}", flush=True)
            if incoming.get("kind") != "chat":
                return
        kind = incoming.get("kind", "chat")
        origin = incoming.get("from", "?")
        text = incoming.get("text", "")
        seq = incoming.get("seq", "?")

        if kind == "hello":
            self.peer_up.set()
            return

        if kind == "reply":
            with self.inbox_lock:
                ev = self.reply_events.get(seq)
                self.replies[seq] = incoming
            if ev is not None:
                ev.set()
            return

        with self.inbox_lock:
            self.inbox.append(incoming)
        print(f"[{self.name} RECV] from={origin} seq={seq} text={text!r}", flush=True)

        if kind == "chat":
            try:
                self._enqueue(self.peer, {
                    "ok": True,
                    "kind": "reply",
                    "heard_by": self.name,
                    "from": origin,
                    "seq": seq,
                    "text": text,
                })
            except Exception as e:
                print(f"[{self.name} REPLY FAIL] {e}", flush=True)

    @internalmethod
    def _write(self, payload: dict) -> None:
        self._enqueue(self.peer, payload)

    @internalmethod
    def _enqueue(self, dest_token: str, payload: dict) -> None:
        boxed = Transponder_Codec.canonicalize(payload)

        def append(obj):
            obj["lanes"].setdefault(dest_token, []).append(boxed)
            obj["present"][self.mine] = {"name": self.name, "ts": time.time()}

        self._mutate(append)

    @dualmethod
    def request_response(self, payload: dict, timeout: float = 5.0) -> dict:
        seq = payload.get("seq")
        ev = threading.Event()
        with self.inbox_lock:
            self.reply_events[seq] = ev
        try:
            self._enqueue(self.peer, payload)
            if not ev.wait(timeout):
                raise TimeoutError(f"no reply for seq={seq}")
            with self.inbox_lock:
                return self.replies.get(seq, {})
        finally:
            with self.inbox_lock:
                self.reply_events.pop(seq, None)

    @dualmethod
    def send_text(self, text: str) -> dict:
        payload = {
            "from": self.name,
            "from_token": self.mine,
            "seq": self.next_seq(),
            "kind": "chat",
            "text": text,
            "ts": time.time(),
        }
        print(f"[{self.name} SEND] seq={payload['seq']} text={text!r}", flush=True)
        reply = self.request_response(payload)
        print(f"[{self.name} REPLY] {reply}", flush=True)
        return reply

    @externalmethod
    def burst(self) -> None:
        pass

    @externalmethod
    def close(self) -> None:
        self.alive.clear()
        if self.watch is not None:
            self.watch.close()
            self.watch = None

        def leave(obj):
            obj.get("present", {}).pop(self.mine, None)
            empty = not obj.get("present")
            return empty

        try:
            empty = self._mutate(leave)
        except Exception:
            empty = False
        if empty:
            for path in (self.bin_path, self.lock_path, self.bin_path + ".tmp"):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

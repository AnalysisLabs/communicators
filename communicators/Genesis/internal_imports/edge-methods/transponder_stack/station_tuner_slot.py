#!/usr/bin/env python3
"""Station / tuner slot prototype (the old "beacon" idea).

Asymmetric on purpose. One station, any number of tuners.
Pulses are UDP unicast copies to a join registry. The station never
waits for a reply and never reads tuner traffic except a one-shot tune
datagram that adds an address to the list.

Terminal 1 (station):
  python station_tuner_slot.py --role station --name WXYZ --listen 127.0.0.1:9101

Terminal 2 (tuner):
  python station_tuner_slot.py --role tuner --name FOX   --listen 127.0.0.1:9102 --peer 127.0.0.1:9101

Terminal 3 (tuner):
  python station_tuner_slot.py --role tuner --name OTTER --listen 127.0.0.1:9103 --peer 127.0.0.1:9101

`--listen` is the local UDP bind.
`--peer` is the station address; required for tuners, unused for the station.

Non-interactive proof:
  python station_tuner_slot.py --role station --name WXYZ --listen 127.0.0.1:9101 --auto --hold 5 --interval 0.4 --repeat 2
  python station_tuner_slot.py --role tuner   --name FOX   --listen 127.0.0.1:9102 --peer 127.0.0.1:9101 --auto --hold 5
  python station_tuner_slot.py --role tuner   --name OTTER --listen 127.0.0.1:9103 --peer 127.0.0.1:9101 --auto --hold 5

Wire framing: one JSON object per UDP datagram. encode at send, decode at recv.
No request_response. No REPLY.

Capability row (harvest later for L1):
  station: listen(join) yes | send yes | recv no | request_response no | serve n/a
  tuner:   listen(pulse) yes | send(tune) once | recv yes | request_response no
"""


class UdpMail:
    """File-local helpers used by both Station and Tuner.

    This is the @modulemethod role: a class both peer classes qualify
    against. Stage C will not rewrite these calls; they stay
    UdpMail.bind_udp(...).
    """

    @externalmethod
    @staticmethod
    def bind_udp(addr: tuple[str, int]) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(addr)
        sock.settimeout(0.3)
        return sock


# ---------------------------------------------------------------------------
# Station
# ---------------------------------------------------------------------------

class Station:
    @internalmethod
    def __init__(self, name: str, listen: tuple[str, int], interval: float, repeat: int):
        self.name = name
        self.listen = listen
        self.interval = max(0.05, interval)
        self.repeat = max(1, repeat)
        self.sock = None
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.registry = {}
        self.reg_lock = threading.Lock()
        self.alive = threading.Event()
        self.join_thread = None

    @dualmethod
    def addr_s(self) -> str:
        return f"udp://{Transponder_Locators.fmt_addr(self.listen)}"

    @dualmethod
    def start(self) -> None:
        self.sock = UdpMail.bind_udp(self.listen)
        self.alive.set()
        self.join_thread = threading.Thread(target=self._join_loop, name=f"{self.name}-join", daemon=True)
        self.join_thread.start()
        print(f"[{self.name} STATION] join-mailbox {self.addr_s()}", flush=True)

    @internalmethod
    def _join_loop(self) -> None:
        while self.alive.is_set():
            try:
                raw, src = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = Transponder_Codec.decode_msg(raw)
            except Exception as e:
                print(f"[{self.name} BAD JSON] from={src} {e}", flush=True)
                continue
            if msg.get("kind") != "tune":
                print(f"[{self.name} IGNORE] kind={msg.get('kind')!r} from={src}", flush=True)
                continue
            recv_s = msg.get("recv") or Transponder_Locators.fmt_addr(src)
            try:
                dest = Transponder_Locators.parse_hostport(str(recv_s))
            except ValueError:
                dest = (src[0], src[1])
            entry = {"name": msg.get("name") or "?", "recv": dest, "ts": time.time()}
            with self.reg_lock:
                self.registry[dest] = entry
            print(f"[{self.name} JOIN] {entry['name']} → {Locators.fmt_addr(dest)}  n={len(self.registry)}", flush=True)

    @dualmethod
    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    @internalmethod
    def _destinations(self) -> list[tuple[tuple[str, int], str]]:
        with self.reg_lock:
            return [(dest, rec["name"]) for dest, rec in self.registry.items()]

    @dualmethod
    def emit(self) -> None:
        seq = self.next_seq()
        payload = {
            "from": self.name,
            "kind": "pulse",
            "seq": seq,
            "text": f"pulse {seq}",
            "ts": time.time(),
        }
        data = Transponder_Codec.encode_bytes(payload)
        dests = self._destinations()
        print(
            f"[{self.name} PULSE] seq={seq} text={payload['text']!r} → {len(dests)} tuner(s)",
            flush=True,
        )
        for dest, _tname in dests:
            for _k in range(self.repeat):
                try:
                    self.sock.sendto(data, dest)
                except OSError as e:
                    print(f"[{self.name} SEND FAIL] {Transponder_Locators.fmt_addr(dest)} {e}", flush=True)

    @externalmethod
    def run(self, hold: float | None) -> None:
        deadline = None if hold is None else time.time() + hold
        try:
            while self.alive.is_set():
                self.emit()
                if deadline is not None and time.time() >= deadline:
                    return
                time.sleep(self.interval)
        except KeyboardInterrupt:
            print(flush=True)

    @externalmethod
    def close(self) -> None:
        self.alive.clear()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        print(f"[{self.name} CLOSE] {self.addr_s()} registry={len(self.registry)}", flush=True)


# ---------------------------------------------------------------------------
# Tuner
# ---------------------------------------------------------------------------

class Tuner:
    @internalmethod
    def __init__(self, name: str, listen: tuple[str, int], station: tuple[str, int]):
        self.name = name
        self.listen = listen
        self.station = station
        self.sock = None
        self.alive = threading.Event()
        self.inbox = []
        self.seen = set()
        self.recv_thread = None

    @dualmethod
    def addr_s(self) -> str:
        return f"udp://{Transponder_Locators.fmt_addr(self.listen)}"

    @dualmethod
    def start(self) -> None:
        self.sock = UdpMail.bind_udp(self.listen)
        self.alive.set()
        self.recv_thread = threading.Thread(target=self._recv_loop, name=f"{self.name}-recv", daemon=True)
        self.recv_thread.start()
        print(
            f"[{self.name} TUNER] recv {self.addr_s()}  station udp://{Transponder_Locators.fmt_addr(self.station)}",
            flush=True,
        )

    @externalmethod
    def tune(self) -> None:
        payload = {
            "kind": "tune",
            "name": self.name,
            "recv": Transponder_Locators.fmt_addr(self.listen),
            "ts": time.time(),
        }
        self.sock.sendto(Transponder_Codec.encode_bytes(payload), self.station)
        print(f"[{self.name} TUNE] sent to {Transponder_Locators.fmt_addr(self.station)} recv={Transponder_Locators.fmt_addr(self.listen)}", flush=True)

    @externalmethod
    def wait_for_station(self, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.tune()
            time.sleep(0.25)
            if self.inbox:
                print(f"[{self.name} STATION UP] first pulse in inbox", flush=True)
                return
        print(f"[{self.name} STATION WAIT] timed out; still listening", flush=True)

    @internalmethod
    def _recv_loop(self) -> None:
        while self.alive.is_set():
            try:
                raw, src = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                incoming = Transponder_Codec.decode_msg(raw)
            except Exception as e:
                print(f"[{self.name} BAD JSON] {e}: {raw!r}", flush=True)
                continue
            kind = incoming.get("kind", "?")
            if kind != "pulse":
                print(f"[{self.name} IGNORE] kind={kind!r} from={src}", flush=True)
                continue
            seq = incoming.get("seq")
            key = (incoming.get("from"), seq)
            if key in self.seen:
                print(f"[{self.name} DUP] seq={seq} (redundant copy ignored)", flush=True)
                continue
            self.seen.add(key)
            self.inbox.append(incoming)
            text = incoming.get("text", "")
            origin = incoming.get("from", "?")
            print(f"[{self.name} RECV] from={origin} seq={seq} text={text!r}", flush=True)

    @externalmethod
    def run(self, hold: float | None) -> None:
        if hold is not None:
            time.sleep(hold)
            return
        print(f"[{self.name} READY] listening for pulses, Ctrl-C to quit", flush=True)
        try:
            while self.alive.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            print(flush=True)

    @externalmethod
    def close(self) -> None:
        self.alive.clear()
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        print(f"[{self.name} CLOSE] {self.addr_s()} heard={len(self.inbox)}", flush=True)

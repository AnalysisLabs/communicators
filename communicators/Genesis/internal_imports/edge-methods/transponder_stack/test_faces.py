#!/usr/bin/env python3
"""Prove NegativeCom/PositiveCom sender/receiver over Wire + duplex slots."""

from __future__ import annotations

import threading
import time
import traceback
import uuid

from transponder_module import NegativeCom, PositiveCom
from wire import Wire


def reset_faces():
    NegativeCom._instance = None
    PositiveCom._instance = None


def attach_pair(scheme: str, ref: dict, timeout: float = 10.0):
    reset_faces()
    pos = PositiveCom({"positive_address": {"port": 0}})
    neg = NegativeCom({})

    results = {}

    def boot_pos():
        try:
            w = Wire(favored=scheme)
            w.attach(
                name="POS",
                ref=ref,
                on_message=lambda msg: pos.receiver(w, msg),
                timeout=timeout,
                schemes=[scheme],
            )
            pos.attach_wire(w)
            results["pos"] = w
        except Exception:
            results["pos_err"] = traceback.format_exc()

    def boot_neg():
        time.sleep(0.15)
        try:
            w = Wire(favored=scheme)
            w.attach(
                name="NEG",
                ref=ref,
                on_message=lambda msg: neg.receiver(w, msg),
                timeout=timeout,
                schemes=[scheme],
            )
            neg.attach_wire(w)
            results["neg"] = w
        except Exception:
            results["neg_err"] = traceback.format_exc()

    t1 = threading.Thread(target=boot_pos)
    t2 = threading.Thread(target=boot_neg)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    if "pos_err" in results or "neg_err" in results:
        raise RuntimeError(f"attach failed\nPOS:{results.get('pos_err')}\nNEG:{results.get('neg_err')}")
    return pos, neg, results["pos"], results["neg"]


def exchange(scheme: str, ref: dict) -> dict:
    pos, neg, wpos, wneg = attach_pair(scheme, ref)
    token = f"tok-{scheme}-{uuid.uuid4().hex[:8]}"
    payload = {
        "communicator_token": token,
        "text": f"{scheme}-fox-sends-a-persistent-line",
        "kind": "freight",
    }
    seen = {"pos_got": None}

    # After negative sends, positive from_P echoes. Capture inbound on pos via queue.
    def send_from_neg():
        neg.to_N(payload)

    t = threading.Thread(target=send_from_neg)
    t.start()
    t.join(timeout=8)
    if t.is_alive():
        wpos.close()
        wneg.close()
        raise TimeoutError(f"{scheme}: to_N / wait_for_echo hung")

    # Positive should have processed the freight line.
    # Give the inbound a moment to land if echo path was faster.
    deadline = time.time() + 3
    while time.time() < deadline:
        for msg in list(pos.up_queue) + list(getattr(pos, "down_queue", [])):
            if msg.get("text") == payload["text"]:
                seen["pos_got"] = msg
                break
        if seen["pos_got"]:
            break
        time.sleep(0.05)

    # Also inspect token map — proves receiver ran.
    mapped = token in pos.ws_token_dict
    scheme_used = wneg.scheme
    wpos.close()
    wneg.close()
    return {
        "scheme": scheme_used,
        "neg_finished": not t.is_alive(),
        "token_mapped": mapped,
        "pos_saw_text": seen["pos_got"] is not None or mapped,
    }


def test_fallback_tcp_to_unix():
    """tcp bind on port 1 should fail (or be unusable); unix path succeeds."""
    reset_faces()
    pos = PositiveCom({"positive_address": {"port": 0}})
    neg = NegativeCom({})
    ref = {
        # Not a host:port, so TcpSlot construction fails and Wire walks to unix.
        "inet": "not-a-tcp-address",
        "path": "/tmp/wire_fallback_demo.sock",
    }
    results = {}

    def boot(face, name, delay):
        time.sleep(delay)
        w = Wire(favored="tcp", scope="loopback")
        w.attach(
            name=name,
            ref=ref,
            on_message=lambda msg: face.receiver(w, msg),
            timeout=6.0,
        )
        face.attach_wire(w)
        results[name] = w

    t1 = threading.Thread(target=boot, args=(pos, "POS", 0))
    t2 = threading.Thread(target=boot, args=(neg, "NEG", 0.2))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    if "POS" not in results or "NEG" not in results:
        raise RuntimeError(f"fallback attach failed: {results}")
    assert results["POS"].scheme == "unix", results["POS"].scheme
    assert results["NEG"].scheme == "unix", results["NEG"].scheme
    token = "tok-fallback"
    done = []

    def send():
        neg.to_N({"communicator_token": token, "text": "fallback-hello", "kind": "freight"})
        done.append(True)

    t = threading.Thread(target=send)
    t.start()
    t.join(timeout=8)
    results["POS"].close()
    results["NEG"].close()
    if not done:
        raise TimeoutError("fallback send hung")
    return {"scheme": results["POS"].scheme, "sent": True}


def main():
    cases = [
        ("tcp", {"inet": "127.0.0.1:19301"}),
        ("unix", {"inet": "/tmp/wire_face_unix.sock", "path": "/tmp/wire_face_unix.sock"}),
        ("ws", {"inet": "127.0.0.1:19311"}),
        ("shm", {
            "inet": "127.0.0.1:19301",
            "mine": "aa11bb22cc33dd44",
            "peer": "ee55ff6677889900",
        }),
    ]
    # shm refs are directional — two faces need swapped tokens
    report = []
    for scheme, ref in cases:
        print(f"\n===== FACE TEST {scheme} =====", flush=True)
        if scheme == "shm":
            reset_faces()
            pos = PositiveCom({"positive_address": {"port": 0}})
            neg = NegativeCom({})
            ref_pos = {"mine": "aa11bb22cc33dd44", "peer": "ee55ff6677889900", "inet": "x"}
            ref_neg = {"mine": "ee55ff6677889900", "peer": "aa11bb22cc33dd44", "inet": "x"}
            errors = {}

            def boot_pos():
                try:
                    w = Wire(favored="shm")
                    w.attach(name="POS", ref=ref_pos, on_message=lambda m: pos.receiver(w, m),
                             timeout=8, schemes=["shm"])
                    pos.attach_wire(w)
                    errors["pos"] = w
                except Exception:
                    errors["pos_err"] = traceback.format_exc()

            def boot_neg():
                try:
                    w = Wire(favored="shm")
                    w.attach(name="NEG", ref=ref_neg, on_message=lambda m: neg.receiver(w, m),
                             timeout=8, schemes=["shm"])
                    neg.attach_wire(w)
                    errors["neg"] = w
                except Exception:
                    errors["neg_err"] = traceback.format_exc()

            t1 = threading.Thread(target=boot_pos)
            t2 = threading.Thread(target=boot_neg)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            if "pos_err" in errors or "neg_err" in errors:
                print(errors.get("pos_err"), errors.get("neg_err"))
                report.append((scheme, False, "attach"))
                continue
            token = "tok-shm-1"
            finished = []

            def send():
                neg.to_N({"communicator_token": token, "text": "shm-fox-sends-a-persistent-line", "kind": "freight"})
                finished.append(True)

            t = threading.Thread(target=send)
            t.start()
            t.join(timeout=8)
            mapped = token in pos.ws_token_dict
            errors["pos"].close()
            errors["neg"].close()
            ok = bool(finished) and mapped
            print("RESULT", {"scheme": "shm", "neg_finished": bool(finished), "token_mapped": mapped})
            report.append((scheme, ok, "ok" if ok else "fail"))
        else:
            try:
                result = exchange(scheme, ref)
                print("RESULT", result)
                ok = result["neg_finished"] and result["token_mapped"]
                report.append((scheme, ok, result))
            except Exception as e:
                print("FAIL", e)
                traceback.print_exc()
                report.append((scheme, False, str(e)))

    print("\n===== FALLBACK tcp -> unix -> shm =====", flush=True)
    try:
        reset_faces()
        pos = PositiveCom({"positive_address": {"port": 0}})
        neg = NegativeCom({})
        ref_base = {
            "inet": "not-a-tcp-address",
            "path": "/proc/wire_cannot_bind.sock",
        }
        ref_pos = dict(ref_base, mine="1111222233334444", peer="5555666677778888")
        ref_neg = dict(ref_base, mine="5555666677778888", peer="1111222233334444")
        got = {}

        def boot(face, name, ref, delay):
            time.sleep(delay)
            w = Wire(favored="tcp", scope="loopback")
            w.attach(name=name, ref=ref, on_message=lambda m: face.receiver(w, m), timeout=6.0)
            face.attach_wire(w)
            got[name] = w

        t1 = threading.Thread(target=boot, args=(pos, "POS", ref_pos, 0))
        t2 = threading.Thread(target=boot, args=(neg, "NEG", ref_neg, 0.1))
        t1.start(); t2.start(); t1.join(); t2.join()
        assert got["POS"].scheme == "shm" and got["NEG"].scheme == "shm"
        done = []

        def send():
            neg.to_N({"communicator_token": "tok-fb-shm", "text": "shm-last-resort", "kind": "freight"})
            done.append(True)

        t = threading.Thread(target=send); t.start(); t.join(timeout=8)
        got["POS"].close(); got["NEG"].close()
        if not done:
            raise TimeoutError("shm last-resort hung")
        print("RESULT", {"scheme": "shm", "sent": True})
        report.append(("fallback-shm", True, "shm"))
    except Exception as e:
        print("FAIL", e)
        traceback.print_exc()
        report.append(("fallback-shm", False, str(e)))

    print("\n===== FALLBACK tcp -> unix =====", flush=True)
    try:
        fb = test_fallback_tcp_to_unix()
        print("RESULT", fb)
        report.append(("fallback", True, fb))
    except Exception as e:
        print("FAIL", e)
        traceback.print_exc()
        report.append(("fallback", False, str(e)))

    print("\n===== SUMMARY =====")
    all_ok = True
    for name, ok, detail in report:
        print(("PASS" if ok else "FAIL"), name, detail)
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

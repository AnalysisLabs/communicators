#!/usr/bin/env python3

# ---------------------------------------------------------------------------
# Transponder Management
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Input Management (parsing)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ouput management (parsing, routing and delivery)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# metamorphosis_writer Mapping (Possibly needed to abstract interface with meta_writer)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Port management (Still critical when namespace is a server)
# ---------------------------------------------------------------------------

def port_in_use(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check if something is listening on (host, port) using a raw TCP connect."""
    if host == "localhost":
        host = "127.0.0.1"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except Exception:
        return False
    finally:
        sock.close()


def kill_port(host: str = "localhost", port: int = 8765) -> None:
    """Aggressively kill anything listening on the port (Linux/macOS)."""
    if host == "localhost":
        host = "127.0.0.1"

    print(f"🔪 Checking/killing port {port}...")
    os.system(f"lsof -t -i:{port} | xargs kill -9 2>/dev/null || true")
    time.sleep(0.4)


# ---------------------------------------------------------------------------
# Server start
# ---------------------------------------------------------------------------



def main() -> None:
    """Boot sequence for the namespace server process."""

    host, port = "localhost", 8765
    if port_in_use(host, port):
        kill_port(host, port)

    print(f"→ (False) Starting namespace server on {host}:{port}")

def secondary() -> None:
    print(f"→ Namespace imported")

if __name__ == "__main__":
    main()
else:
    secondary()


#!/usr/bin/env python3
"""T1 locator parsers. Shared by every inet/path/token slot.

These used to be free functions copied into each prototype. Call them
qualified: Locators.parse_hostport(spec). That is the role a future
@modulemethod would play across classes in one file — except the
callers live in many files, so this is a real T1 class, not a
file-local module class.
"""

class Transponder_Locators:
    TOKEN_RE = re.compile(r"^[0-9A-Fa-f]+$")
    BIN_DIR = "/dev/shm"

    @externalmethod
    @staticmethod
    def parse_hostport(spec: str) -> tuple[str, int]:
        spec = spec.strip()
        if "://" in spec:
            spec = spec.split("://", 1)[1]
        if spec.count(":") != 1:
            raise ValueError(f"expected host:port, got {spec!r}")
        host, port_s = spec.rsplit(":", 1)
        host = "127.0.0.1" if host in ("", "localhost") else host
        return host, int(port_s)

    @externalmethod
    @staticmethod
    def fmt_addr(addr: tuple[str, int]) -> str:
        return f"{addr[0]}:{addr[1]}"

    @externalmethod
    @staticmethod
    def parse_sockpath(spec: str) -> str:
        """Filesystem path, unix://path, or host:port mapped into /tmp."""
        spec = spec.strip()
        if spec.startswith("unix://"):
            spec = spec[len("unix://"):]
        if spec.startswith("unix:"):
            spec = spec[len("unix:"):]
        looks_like_path = (
            spec.startswith("/")
            or spec.startswith("./")
            or spec.startswith("../")
            or spec.endswith(".sock")
            or "/" in spec
        )
        if looks_like_path:
            return spec
        if spec.count(":") == 1:
            host, port_s = spec.rsplit(":", 1)
            if port_s.isdigit():
                host = "127.0.0.1" if host in ("", "localhost") else host
                return f"/tmp/unix_slot_{host}_{port_s}.sock"
        return spec

    @externalmethod
    @staticmethod
    def parse_token(spec: str) -> str:
        spec = spec.strip()
        for prefix in ("shm://", "shm:", "token:"):
            if spec.startswith(prefix):
                spec = spec[len(prefix):]
                break
        if not Transponder_Locators.TOKEN_RE.match(spec):
            raise ValueError(f"token must be hex, got {spec!r}")
        if len(spec) < 8:
            raise ValueError(f"token too short ({len(spec)}); pass a hex communicator token")
        return spec.lower()

    @externalmethod
    @staticmethod
    def shm_bin_paths(token_a: str, token_b: str) -> tuple[str, str]:
        a, b = sorted((token_a, token_b))
        stem = f"comm_slot_{a}_{b}"
        return (
            os.path.join(Transponder_Locators.BIN_DIR, f"{stem}.json"),
            os.path.join(Transponder_Locators.BIN_DIR, f"{stem}.lock"),
        )

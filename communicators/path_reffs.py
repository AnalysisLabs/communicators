from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from functools import lru_cache

# ---------------------------------------------------------------------------
# Reff Making
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileRef:
    """
    Immutable reference to a file tracked in file_registry.json.

    The three fields form the stable identity.
    Call .resolve() when you actually need the real filesystem path.
    """
    uuid: str
    file_path: str
    file_name: str

    def resolve(self, field: str = "absolute_path") -> Path:
        """
        Look up this exact triple in the registry and return the requested field
        (defaults to absolute_path).
        """
        from resolve_path import resolve_path   # or whatever module you put it in
        return Path(resolve_path(self.uuid, self.file_path, self.file_name, field))

    def __str__(self) -> str:
        return f"{self.file_path}/{self.file_name}" if self.file_path else self.file_name

    @classmethod
    def from_entry(cls, entry: dict) -> FileRef:
        """Convenience constructor from a raw registry dict."""
        return cls(
            uuid=entry["uuid"],
            file_path=entry["file_path"],
            file_name=entry["file_name"],
        )

# ---------------------------------------------------------------------------
# Reff Usage
# ---------------------------------------------------------------------------

def find_communicators_root(start=None) -> Path:
    d = Path(start or Path.cwd()).absolute()
    while d != Path("/"):
        if d.name == "communicators":
            return d
        d = d.parent
    return Path.cwd()


@lru_cache(maxsize=1)
def _load_registry() -> list[dict]:
    root = find_communicators_root()
    registry_file = root / "file_registry.json"
    if not registry_file.exists():
        raise FileNotFoundError(f"file_registry.json not found at {registry_file}")
    return json.loads(registry_file.read_text(encoding="utf-8"))


def resolve_path(
    uuid: str,
    file_path: str,
    file_name: str,
    field: str = "absolute_path",
) -> str:
    """
    Strict lookup by the full identity triple.
    Raises FileNotFoundError on any mismatch (broken reference).

    Typical use:
        program_path = Path(resolve_path(
            "8b023d16-a060-477c-88a5-e007d1193377",
            "Genesis/execution",
            "bootloader.py"
        ))
    """
    registry = _load_registry()

    for entry in registry:
        if (entry["uuid"] == uuid
            and entry["file_path"] == file_path
            and entry["file_name"] == file_name):
            if field not in entry:
                raise KeyError(f"Field {field!r} not present in registry entry")
            return Path(entry[field])

    raise FileNotFoundError(
        f"Broken reference: uuid={uuid!r}, file_path={file_path!r}, file_name={file_name!r}"
    )

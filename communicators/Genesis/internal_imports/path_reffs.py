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
    """
    uuid: str
    file_path: str
    file_name: str

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
) -> Path:
    """
    Strict lookup by the full identity triple.
    Returns the absolute Path computed from the current communicators root
    + the relative file_path + file_name stored in the registry.

    Raises FileNotFoundError on any mismatch (broken reference).
    """
    registry = _load_registry()
    root = find_communicators_root()

    for entry in registry:
        if (entry["uuid"] == uuid
            and entry["file_path"] == file_path
            and entry["file_name"] == file_name):

            if file_path:
                return root / file_path / file_name
            else:
                return Path(root / file_name)

    raise FileNotFoundError(
        f"Broken reference: uuid={uuid!r}, file_path={file_path!r}, file_name={file_name!r}"
    )

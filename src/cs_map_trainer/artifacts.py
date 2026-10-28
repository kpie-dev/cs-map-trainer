"""Publish a complete artifact without replacing an existing path."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def write_new_file(path: Path, content: bytes) -> None:
    handle = NamedTemporaryFile(dir=path.parent, prefix=".cmt-", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

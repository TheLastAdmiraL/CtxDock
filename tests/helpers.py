from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class TempHome:
    def __init__(self):
        root = Path.cwd() / ".test-tmp"
        root.mkdir(exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="ctxdock-", dir=root))

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


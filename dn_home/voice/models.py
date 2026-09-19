"""Shared voice data types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


@dataclass(slots=True)
class AudioAsset:
    path: Path
    content_type: str
    temporary_directory: Path | None = None

    def cleanup(self) -> None:
        """Delete generated audio and its private temporary directory."""

        if self.temporary_directory:
            shutil.rmtree(self.temporary_directory, ignore_errors=True)
        else:
            self.path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class Voice:
    name: str
    locale: str
    gender: str


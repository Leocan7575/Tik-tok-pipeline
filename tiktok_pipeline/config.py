"""Gemeinsame Konfiguration: Pfade, .env-Laden, Ausgabeformat."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
PROJEKTE_DIR = REPO_ROOT / "projekte"

# TikTok-Zielformat
BREITE = 1080
HOEHE = 1920
FPS = 30
AUDIO_RATE = 48000


def lade_env() -> None:
    """Liest API-Schlüssel ausschließlich aus der .env-Datei im Repo-Wurzelverzeichnis."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv ist optional, solange keine API genutzt wird
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def env(name: str, pflicht: bool = False) -> str | None:
    wert = os.environ.get(name) or None
    if pflicht and not wert:
        raise SystemExit(
            f"Fehlender API-Schlüssel: {name}. Trage ihn in die Datei .env ein "
            f"(Vorlage: .env.example)."
        )
    return wert


@dataclass
class Projekt:
    """Arbeitsordner eines Durchlaufs: projekte/<name>/..."""

    ordner: Path

    @classmethod
    def aus_name(cls, name: str | None, video: Path | None = None) -> "Projekt":
        if name and (os.sep in name or "/" in name):
            ordner = Path(name)
        else:
            if not name:
                if video is None:
                    raise SystemExit("Bitte --projekt angeben.")
                name = video.stem
            ordner = PROJEKTE_DIR / name
        ordner.mkdir(parents=True, exist_ok=True)
        return cls(ordner.resolve())

    # Dateien
    @property
    def analysis(self) -> Path:
        return self.ordner / "analysis.json"

    @property
    def script(self) -> Path:
        return self.ordner / "script.json"

    @property
    def frames(self) -> Path:
        return self._dir("frames")

    @property
    def clips(self) -> Path:
        return self._dir("clips")

    @property
    def voice(self) -> Path:
        return self._dir("voice")

    @property
    def segmente(self) -> Path:
        return self._dir("build")

    @property
    def ausgabe(self) -> Path:
        return self.ordner / "final.mp4"

    def _dir(self, name: str) -> Path:
        p = self.ordner / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def clip_fuer(self, nr: int) -> Path | None:
        return _finde(self.clips, f"szene_{nr:03d}", (".mp4", ".mov", ".webm"))

    def voice_fuer(self, nr: int) -> Path | None:
        return _finde(self.voice, f"szene_{nr:03d}", (".mp3", ".wav", ".m4a", ".ogg"))


def _finde(ordner: Path, stamm: str, endungen: tuple[str, ...]) -> Path | None:
    for e in endungen:
        p = ordner / f"{stamm}{e}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None

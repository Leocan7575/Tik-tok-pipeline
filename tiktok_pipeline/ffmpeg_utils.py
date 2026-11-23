"""Kleine Helfer rund um ffmpeg/ffprobe."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def pruefe_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} wurde nicht gefunden. Bitte ffmpeg installieren (siehe README).")


def run(cmd: list[str], cwd: Path | None = None, still: bool = True) -> subprocess.CompletedProcess:
    """Führt ffmpeg/ffprobe aus und zeigt bei Fehlern die letzten Zeilen der Ausgabe."""
    if still and cmd and Path(cmd[0]).name == "ffmpeg":
        cmd = [cmd[0], "-hide_banner", "-loglevel", "error", "-y", *cmd[1:]]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = "\n".join((res.stderr or res.stdout).strip().splitlines()[-15:])
        raise RuntimeError(f"Befehl fehlgeschlagen: {' '.join(map(str, cmd))}\n{tail}")
    return res


def probe(pfad: Path) -> dict:
    res = run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(pfad)],
        still=False,
    )
    return json.loads(res.stdout)


def video_info(pfad: Path) -> dict:
    """Dauer, Auflösung, FPS und ob eine Tonspur existiert."""
    daten = probe(pfad)
    v = next((s for s in daten["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in daten["streams"] if s.get("codec_type") == "audio"), None)
    dauer = float(daten.get("format", {}).get("duration") or (v or {}).get("duration") or 0)
    info = {"dauer": round(dauer, 3), "hat_ton": a is not None}
    if v:
        num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").partition("/")
        fps = float(num) / float(den or 1) if float(den or 1) else 30.0
        breite, hoehe = int(v["width"]), int(v["height"])
        # Hochkant-Videos vom Handy speichern die Drehung oft als Metadatum
        rot = _rotation(v)
        if rot in (90, 270):
            breite, hoehe = hoehe, breite
        info.update({"breite": breite, "hoehe": hoehe, "fps": round(fps, 3)})
    return info


def _rotation(stream: dict) -> int:
    rot = stream.get("tags", {}).get("rotate")
    if rot is None:
        for sd in stream.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = sd["rotation"]
    try:
        return abs(int(float(rot))) % 360
    except (TypeError, ValueError):
        return 0


def dauer(pfad: Path) -> float:
    daten = probe(pfad)
    return float(daten.get("format", {}).get("duration") or 0)


def filter_pfad(pfad: Path | str) -> str:
    """Pfad so escapen, dass er in einem ffmpeg-Filterargument (ass=..., fontsdir=...) funktioniert."""
    s = str(pfad).replace("\\", "/")
    for zeichen in ("\\", ":", "'", ",", "[", "]", ";"):
        s = s.replace(zeichen, "\\" + zeichen)
    return s

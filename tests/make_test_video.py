"""Erzeugt ein synthetisches Hochkant-Testvideo mit harten Schnitten (nur ffmpeg, keine Fremdinhalte).

    python tests/make_test_video.py testvideo.mp4
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# (Quelle, Dauer in s) – bewusst unterschiedliche Bildinhalte, damit jeder Schnitt erkennbar ist
SZENEN = [
    ("testsrc2=s=720x1280:r=30", 1.6),
    ("mandelbrot=s=720x1280:r=30", 2.2),
    ("color=c=red:s=720x1280:r=30", 0.9),
    ("smptehdbars=s=720x1280:r=30", 1.4),
    ("life=s=720x1280:r=30:mold=10:ratio=0.2:death_color=#102030:life_color=#ffcc00", 2.5),
    ("color=c=0x2255ff:s=720x1280:r=30", 1.1),
]


def main(ziel: str) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for quelle, d in SZENEN:
        cmd += ["-f", "lavfi", "-t", str(d), "-i", quelle]
    gesamt = sum(d for _, d in SZENEN)
    cmd += ["-f", "lavfi", "-t", str(gesamt), "-i", "sine=f=330:b=2:r=48000"]
    n = len(SZENEN)
    filt = "".join(f"[{i}:v]format=yuv420p,setsar=1[v{i}];" for i in range(n))
    filt += "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    cmd += ["-filter_complex", filt, "-map", "[v]", "-map", f"{n}:a", "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-shortest", ziel]
    subprocess.run(cmd, check=True)
    print(f"Testvideo: {ziel} ({gesamt:.1f}s, {n} Szenen)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "testvideo.mp4")

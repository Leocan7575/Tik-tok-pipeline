"""TikTok-Untertitel: kurze Wortgruppen, große fette Schrift, Kontur, Pop-Animation (ASS + SRT)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import BREITE, HOEHE


@dataclass
class Stil:
    schrift: str = "Montserrat Black"
    groesse: int = 104
    farbe: str = "#FFFFFF"
    kontur_farbe: str = "#000000"
    kontur: float = 7.0
    schatten: float = 3.0
    # Abstand vom unteren Rand. TikTok überdeckt unten ~25 % mit Beschreibung/Buttons.
    rand_unten: int = 620
    rand_seite: int = 90
    grossbuchstaben: bool = True
    max_woerter: int = 3
    max_zeichen: int = 16
    pop: bool = True


@dataclass
class Zeile:
    start: float
    ende: float
    text: str
    farbe: str | None = None  # optionale Sprecherfarbe
    stil: str = "TikTok"      # "TikTok" = Untertitel, "Einblendung" = großer Comic-Text (z. B. "HAB DICH!")


def _ass_farbe(hexfarbe: str, alpha: int = 0) -> str:
    h = hexfarbe.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _zeit_ass(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _zeit_srt(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wortgruppen(text: str, max_woerter: int = 3, max_zeichen: int = 18) -> list[str]:
    """Teilt einen Dialog in kurze, schnell lesbare Häppchen (TikTok-Stil)."""
    woerter = text.split()
    gruppen: list[list[str]] = []
    aktuell: list[str] = []
    for w in woerter:
        kandidat = " ".join(aktuell + [w])
        if aktuell and (len(aktuell) >= max_woerter or len(kandidat) > max_zeichen):
            gruppen.append(aktuell)
            aktuell = []
        aktuell.append(w)
        if re.search(r"[.!?…]$", w):  # Satzende -> neue Gruppe
            gruppen.append(aktuell)
            aktuell = []
    if aktuell:
        gruppen.append(aktuell)
    return [" ".join(g) for g in gruppen]


def zeilen_fuer_dialog(text: str, start: float, ende: float, stil: Stil, farbe: str | None = None) -> list[Zeile]:
    """Verteilt die Wortgruppen proportional zur Zeichenanzahl über [start, ende]."""
    gruppen = wortgruppen(text, stil.max_woerter, stil.max_zeichen)
    if not gruppen or ende <= start:
        return []
    gewichte = [len(g) + 3 for g in gruppen]
    summe = sum(gewichte)
    zeilen, t = [], start
    for g, gw in zip(gruppen, gewichte):
        d = (ende - start) * gw / summe
        zeilen.append(Zeile(t, t + d, g, farbe))
        t += d
    return zeilen


def _ass_text(text: str, stil: Stil, farbe: str | None, einblendung: bool = False) -> str:
    t = text.upper() if stil.grossbuchstaben or einblendung else text
    t = t.replace("\\", "/").replace("{", "(").replace("}", ")")
    tags = ""
    if einblendung:
        tags += r"\fscx30\fscy30\t(0,120,\fscx115\fscy115)\t(120,200,\fscx100\fscy100)"
    elif stil.pop:
        tags += r"\fscx70\fscy70\t(0,90,\fscx108\fscy108)\t(90,150,\fscx100\fscy100)"
    if farbe:
        tags += rf"\c{_ass_farbe(farbe)}"
    return ("{" + tags + "}" if tags else "") + t


def schreibe_ass(zeilen: list[Zeile], ziel: Path, stil: Stil | None = None) -> None:
    stil = stil or Stil()
    kopf = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {BREITE}
PlayResY: {HOEHE}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Einblendung,{stil.schrift},{int(stil.groesse * 1.7)},{_ass_farbe('#FFE600')},{_ass_farbe('#FFE600')},{_ass_farbe('#000000')},{_ass_farbe('#000000', 0x40)},0,0,0,0,100,100,2,-6,1,12,6,8,60,60,330,1
Style: TikTok,{stil.schrift},{stil.groesse},{_ass_farbe(stil.farbe)},{_ass_farbe(stil.farbe)},{_ass_farbe(stil.kontur_farbe)},{_ass_farbe('#000000', 0x60)},0,0,0,0,100,100,1,0,1,{stil.kontur},{stil.schatten},2,{stil.rand_seite},{stil.rand_seite},{stil.rand_unten},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    zeilen_txt = [
        f"Dialogue: {1 if z.stil == 'Einblendung' else 0},{_zeit_ass(z.start)},{_zeit_ass(z.ende)},{z.stil},,0,0,0,,"
        f"{_ass_text(z.text, stil, z.farbe, z.stil == 'Einblendung')}"
        for z in zeilen
    ]
    ziel.write_text(kopf + "\n".join(zeilen_txt) + "\n", encoding="utf-8")


def schreibe_srt(zeilen: list[Zeile], ziel: Path) -> None:
    zeilen = sorted((z for z in zeilen if z.stil == "TikTok"), key=lambda z: z.start)
    bloecke = [f"{i}\n{_zeit_srt(z.start)} --> {_zeit_srt(z.ende)}\n{z.text}\n"
               for i, z in enumerate(zeilen, start=1)]
    ziel.write_text("\n".join(bloecke), encoding="utf-8")

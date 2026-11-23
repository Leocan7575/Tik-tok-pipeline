"""Schritt 6 – assemble: Clips schneiden, Ton anlegen, Untertitel einbrennen, Musik, Export 1080x1920.

Läuft lokal mit ffmpeg, ohne bezahlte APIs.
Eingaben:  <projekt>/script.json, <projekt>/clips/szene_XXX.mp4, <projekt>/voice/szene_XXX.mp3
Ausgabe:   <projekt>/final.mp4 (+ final.srt)

Fehlt ein Clip, wird (mit --platzhalter, Standard) eine Platzhalter-Tafel gerendert, so dass
Timing, Ton und Untertitel schon vor dem Generieren geprüft werden können (Animatic).
"""
from __future__ import annotations

import hashlib
import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

from .config import AUDIO_RATE, BREITE, FONTS_DIR, FPS, HOEHE, Projekt
from .ffmpeg_utils import dauer as mediendauer
from .ffmpeg_utils import filter_pfad, pruefe_ffmpeg, run, video_info
from .subtitles import Stil, Zeile, schreibe_ass, schreibe_srt, zeilen_fuer_dialog

SEGMENT_VERSION = 2  # erhöhen, wenn sich das Segment-Rendering ändert (invalidiert den Cache)
PLATZHALTER_FARBEN = ["0x26215c", "0x0f4c5c", "0x5f0f40", "0x1b4332", "0x3a0ca3", "0x7f4f24"]


@dataclass
class SzenenPlan:
    nr: int
    dauer: float
    dialog: str
    sprecher: str | None
    clip: Path | None
    voice: Path | None
    voice_dauer: float
    dialog_start: float
    prompt: str


def lade_script(projekt: Projekt) -> dict:
    if not projekt.script.exists():
        raise SystemExit(f"{projekt.script} fehlt. Zuerst 'python pipeline.py script ...' ausführen.")
    return json.loads(projekt.script.read_text(encoding="utf-8"))


def plane_szenen(script: dict, projekt: Projekt, min_luft: float = 0.15) -> list[SzenenPlan]:
    plaene = []
    for sz in script["szenen"]:
        nr = int(sz["nr"])
        voice = projekt.voice_fuer(nr)
        vd = mediendauer(voice) if voice else 0.0
        start = float(sz.get("dialog_start", 0.08 if voice else 0.0))
        soll = float(sz.get("dauer") or 2.0)
        # Ist die Sprachaufnahme länger als die geplante Szene, wird die Szene verlängert
        # (das Bild friert am Ende ein), damit kein Satz abgeschnitten wird.
        d = max(soll, start + vd + min_luft) if voice else soll
        plaene.append(SzenenPlan(
            nr=nr, dauer=round(d, 3), dialog=(sz.get("dialog") or "").strip(),
            sprecher=sz.get("sprecher"), clip=projekt.clip_fuer(nr), voice=voice, voice_dauer=vd,
            dialog_start=start, prompt=sz.get("prompt") or "",
        ))
    return plaene


# ---------------------------------------------------------------------------
# Segment pro Szene
# ---------------------------------------------------------------------------


def _cache_schluessel(p: SzenenPlan, clip_ton: float) -> str:
    teile = [SEGMENT_VERSION, p.nr, p.dauer, p.dialog_start, clip_ton]
    for f in (p.clip, p.voice):
        teile.append(f"{f}:{f.stat().st_mtime_ns}:{f.stat().st_size}" if f else "-")
    if not p.clip:
        teile.append(p.prompt)
    return hashlib.sha1(json.dumps(teile, default=str).encode()).hexdigest()


def rendere_segment(p: SzenenPlan, projekt: Projekt, clip_ton: float = 0.0, preset: str = "medium",
                    platzhalter: bool = True, erzwingen: bool = False) -> Path:
    ziel = projekt.segmente / f"szene_{p.nr:03d}.mkv"
    meta = ziel.with_suffix(".json")
    schluessel = _cache_schluessel(p, clip_ton)
    if not erzwingen and ziel.exists() and meta.exists():
        if json.loads(meta.read_text()).get("schluessel") == schluessel:
            return ziel

    D = p.dauer
    cmd = ["ffmpeg"]
    vf_basis = (f"scale={BREITE}:{HOEHE}:force_original_aspect_ratio=increase,crop={BREITE}:{HOEHE},"
                f"setsar=1,fps={FPS}")
    clip_hat_ton = False
    if p.clip:
        cmd += ["-i", str(p.clip)]
        clip_hat_ton = video_info(p.clip)["hat_ton"]
        vkette = f"[0:v]{vf_basis},tpad=stop_mode=clone:stop_duration={D:.3f}," \
                 f"trim=duration={D:.3f},setpts=PTS-STARTPTS,format=yuv420p[v]"
    elif platzhalter:
        txt = projekt.segmente / f"szene_{p.nr:03d}_platzhalter.txt"
        txt.write_text(_platzhalter_text(p), encoding="utf-8")
        farbe = PLATZHALTER_FARBEN[(p.nr - 1) % len(PLATZHALTER_FARBEN)]
        cmd += ["-f", "lavfi", "-i", f"color=c={farbe}:s={BREITE}x{HOEHE}:r={FPS}:d={D:.3f}"]
        font = filter_pfad(FONTS_DIR / "Montserrat-Black.ttf")
        vkette = (f"[0:v]drawtext=fontfile={font}:text='SZENE {p.nr}':fontsize=120:fontcolor=white:"
                  f"x=(w-text_w)/2:y=300:borderw=6:bordercolor=black,"
                  f"drawtext=fontfile={font}:textfile={filter_pfad(txt)}:fontsize=40:fontcolor=white@0.85:"
                  f"x=90:y=520:line_spacing=14,"
                  f"drawtext=fontfile={font}:text='%{{pts\\:hms}}':fontsize=40:fontcolor=white@0.6:x=90:y=h-200,"
                  f"setsar=1,format=yuv420p[v]")
    else:
        raise SystemExit(f"Clip für Szene {p.nr} fehlt ({projekt.clips}/szene_{p.nr:03d}.mp4).")

    a_idx = 1
    if p.voice:
        cmd += ["-i", str(p.voice)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{D:.3f}", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
    fmt = f"aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo"
    delay_ms = int(round(p.dialog_start * 1000)) if p.voice else 0
    akette = f"[{a_idx}:a]{fmt},adelay={delay_ms}:all=1,apad,atrim=duration={D:.3f},asetpts=PTS-STARTPTS"
    if clip_ton > 0 and clip_hat_ton:
        akette += "[vo];"
        akette += (f"[0:a]{fmt},volume={clip_ton},apad,atrim=duration={D:.3f},asetpts=PTS-STARTPTS[ca];"
                   f"[vo][ca]amix=inputs=2:normalize=0:duration=first[a]")
    else:
        akette += "[a]"

    cmd += ["-filter_complex", f"{vkette};{akette}", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", preset, "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE), "-ac", "2", "-t", f"{D:.3f}", str(ziel)]
    run(cmd)
    meta.write_text(json.dumps({"schluessel": schluessel, "dauer": D}), encoding="utf-8")
    return ziel


def _platzhalter_text(p: SzenenPlan) -> str:
    zeilen = ["PLATZHALTER (noch kein Clip)", ""]
    if p.prompt:
        zeilen += textwrap.wrap(p.prompt, 38)[:14]
    if p.sprecher or p.dialog:
        zeilen += ["", f"{(p.sprecher or '?').upper()}:"] + textwrap.wrap(p.dialog, 38)[:4]
    # drawtext interpretiert % als Ausdruck
    return "\n".join(zeilen).replace("%", "%%")


# ---------------------------------------------------------------------------
# Gesamtvideo
# ---------------------------------------------------------------------------


def baue_untertitel(plaene: list[SzenenPlan], script: dict, stil: Stil, wps: float = 2.6) -> list[Zeile]:
    farben = {f.get("id"): f.get("untertitel_farbe") for f in script.get("figuren", [])}
    zeilen, t = [], 0.0
    for p in plaene:
        if p.dialog:
            start = t + p.dialog_start
            if p.voice:
                ende = start + p.voice_dauer
            else:  # ohne Sprachaufnahme: Lesedauer schätzen
                ende = min(t + p.dauer - 0.05, start + max(0.8, len(p.dialog.split()) / wps))
            zeilen += zeilen_fuer_dialog(p.dialog, start, ende, stil, farben.get(p.sprecher))
        t += p.dauer
    return zeilen


def assemble(projekt: Projekt, musik: Path | None = None, musik_lautstaerke: float = 0.12,
             clip_ton: float = 0.0, untertitel: bool = True, platzhalter: bool = True,
             grossbuchstaben: bool = True, preset: str = "medium", lautheit: float | None = -14.0,
             ausgabe: Path | None = None, neu_rendern: bool = False) -> Path:
    pruefe_ffmpeg()
    script = lade_script(projekt)
    plaene = plane_szenen(script, projekt)
    gesamt = round(sum(p.dauer for p in plaene), 3)
    fehlend = [p.nr for p in plaene if not p.clip]
    print(f"[assemble] {len(plaene)} Szenen, Gesamtdauer {gesamt:.2f}s")
    if fehlend:
        hinweis = "Platzhalter-Tafeln" if platzhalter else "FEHLER"
        print(f"[assemble] Ohne Clip ({hinweis}): Szenen {', '.join(map(str, fehlend))}")
        if not platzhalter:
            raise SystemExit("Fehlende Clips – erst 'generate' ausführen oder --platzhalter verwenden.")

    segmente = []
    for p in plaene:
        print(f"[assemble]   Szene {p.nr:>2}: {p.dauer:5.2f}s  "
              f"clip={'ja' if p.clip else 'platzhalter'}  voice={'ja' if p.voice else 'nein'}")
        segmente.append(rendere_segment(p, projekt, clip_ton, preset, platzhalter, neu_rendern))

    liste = projekt.segmente / "segmente.txt"
    liste.write_text("".join(f"file '{s.name}'\n" for s in segmente), encoding="utf-8")

    stil = Stil(grossbuchstaben=grossbuchstaben)
    zeilen = baue_untertitel(plaene, script, stil) if untertitel else []
    ass = projekt.segmente / "untertitel.ass"
    schreibe_ass(zeilen, ass, stil)
    ziel = (ausgabe or projekt.ausgabe).resolve()
    schreibe_srt(zeilen, ziel.with_suffix(".srt"))

    cmd = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", liste.name]
    vf = f"[0:v]ass={ass.name}:fontsdir={filter_pfad(FONTS_DIR)}[v]" if zeilen else "[0:v]null[v]"
    nach = f"aresample={AUDIO_RATE}"
    if lautheit is not None:
        nach = f"loudnorm=I={lautheit}:TP=-1.5:LRA=11,{nach}"
    if musik:
        cmd += ["-stream_loop", "-1", "-i", str(Path(musik).resolve())]
        fade = max(0.0, gesamt - 1.5)
        af = (f"[1:a]aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,volume={musik_lautstaerke},"
              f"atrim=duration={gesamt:.3f},afade=t=in:d=0.3,afade=t=out:st={fade:.3f}:d=1.5[m];"
              f"[0:a]asplit=2[vo][sc];"
              # Ducking: Musik wird leiser, sobald gesprochen wird
              f"[m][sc]sidechaincompress=threshold=0.02:ratio=8:attack=10:release=400[md];"
              f"[vo][md]amix=inputs=2:normalize=0:duration=first,{nach}[a]")
    else:
        af = f"[0:a]{nach}[a]"

    cmd += ["-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", preset, "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE),
            "-movflags", "+faststart", "-t", f"{gesamt:.3f}", str(ziel)]
    print("[assemble] Rendere Endvideo ...")
    run(cmd, cwd=projekt.segmente)
    info = video_info(ziel)
    print(f"[assemble] Fertig: {ziel}  ({info.get('breite')}x{info.get('hoehe')}, {info['dauer']:.2f}s)")
    return ziel

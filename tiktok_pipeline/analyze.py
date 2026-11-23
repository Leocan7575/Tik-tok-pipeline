"""Schritt 1 – analyze: Szenen erkennen, Standbilder speichern, Ton transkribieren.

Läuft komplett lokal (ffmpeg, PySceneDetect, OpenCV, faster-whisper) ohne bezahlte APIs.
Ergebnis: <projekt>/analysis.json, <projekt>/frames/szene_XXX.jpg, <projekt>/kontaktbogen.jpg
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import Projekt
from .ffmpeg_utils import pruefe_ffmpeg, run, video_info

# ---------------------------------------------------------------------------
# Szenenerkennung
# ---------------------------------------------------------------------------


def erkenne_szenen(video: Path, info: dict, schwelle: float | None = None,
                   min_laenge: float = 0.35) -> tuple[list[tuple[float, float]], str]:
    """Liefert eine Liste (start, ende) in Sekunden und die verwendete Methode."""
    fps = info.get("fps") or 30.0
    try:
        from scenedetect import AdaptiveDetector, ContentDetector, detect

        min_frames = max(1, int(round(min_laenge * fps)))
        if schwelle is None:
            # AdaptiveDetector kommt mit schnellen Kamerabewegungen (typisch für TikTok) besser klar
            detektor = AdaptiveDetector(min_scene_len=min_frames)
            methode = "pyscenedetect-adaptive"
        else:
            detektor = ContentDetector(threshold=schwelle, min_scene_len=min_frames)
            methode = f"pyscenedetect-content(threshold={schwelle})"
        liste = detect(str(video), detektor, start_in_scene=True)
        szenen = [(s.seconds, e.seconds) for s, e in liste]
    except ImportError:
        szenen, methode = _szenen_ffmpeg(video, info, schwelle or 0.3, min_laenge), "ffmpeg-scene"

    if not szenen:
        szenen = [(0.0, info["dauer"])]
    # Letzte Szene bis zum echten Videoende ziehen
    s0, e0 = szenen[-1]
    if info["dauer"] and info["dauer"] - e0 < 0.5:
        szenen[-1] = (s0, info["dauer"])
    return [(round(s, 3), round(e, 3)) for s, e in szenen], methode


def _szenen_ffmpeg(video: Path, info: dict, schwelle: float, min_laenge: float) -> list[tuple[float, float]]:
    """Fallback ohne PySceneDetect: ffmpeg-Filter select='gt(scene,x)'."""
    if schwelle > 1:  # ContentDetector-Skala (0-100) grob auf ffmpeg-Skala (0-1) abbilden
        schwelle = schwelle / 100
    res = run(["ffmpeg", "-hide_banner", "-i", str(video), "-an", "-vf",
               f"select='gt(scene,{schwelle})',showinfo", "-f", "null", "-"], still=False)
    zeiten = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", res.stderr)]
    grenzen = [0.0]
    for t in zeiten:
        if t - grenzen[-1] >= min_laenge:
            grenzen.append(t)
    grenzen.append(info["dauer"])
    return [(grenzen[i], grenzen[i + 1]) for i in range(len(grenzen) - 1) if grenzen[i + 1] > grenzen[i]]


# ---------------------------------------------------------------------------
# Standbilder + Bildmerkmale
# ---------------------------------------------------------------------------


def speichere_standbild(video: Path, zeit: float, ziel: Path) -> None:
    run(["ffmpeg", "-ss", f"{zeit:.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(ziel)])


def bild_merkmale(bild: Path) -> dict:
    """Einfache, lokale Merkmale: Helligkeit, Sättigung, dominante Farben."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {}
    img = cv2.imread(str(bild))
    if img is None:
        return {}
    klein = cv2.resize(img, (64, int(64 * img.shape[0] / img.shape[1])))
    hsv = cv2.cvtColor(klein, cv2.COLOR_BGR2HSV)
    pixel = klein.reshape(-1, 3).astype(np.float32)
    kriterien = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    k = min(4, len(pixel))
    _, labels, zentren = cv2.kmeans(pixel, k, None, kriterien, 3, cv2.KMEANS_PP_CENTERS)
    anteile = np.bincount(labels.flatten(), minlength=k) / len(labels)
    farben = sorted(zip(anteile, zentren), key=lambda x: -x[0])
    return {
        "helligkeit": round(float(hsv[..., 2].mean()) / 255, 3),
        "saettigung": round(float(hsv[..., 1].mean()) / 255, 3),
        "dominante_farben": [
            {"hex": "#{:02x}{:02x}{:02x}".format(int(c[2]), int(c[1]), int(c[0])), "anteil": round(float(a), 2)}
            for a, c in farben
        ],
    }


def bewegung_pro_szene(video: Path, szenen: list[tuple[float, float]], proben_pro_sek: float = 6.0) -> list[float]:
    """Mittlere Bilddifferenz innerhalb jeder Szene (0 = statisch, ~1 = sehr viel Bewegung)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return [0.0] * len(szenen)
    cap = cv2.VideoCapture(str(video))
    werte = []
    for start, ende in szenen:
        diffs, vorher = [], None
        t = start + 0.02
        while t < ende - 0.02:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            grau = cv2.cvtColor(cv2.resize(frame, (96, 96)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            if vorher is not None:
                diffs.append(float(np.abs(grau - vorher).mean()) / 255)
            vorher = grau
            t += 1.0 / proben_pro_sek
        werte.append(round(min(1.0, (sum(diffs) / len(diffs)) * 8) if diffs else 0.0, 3))
    cap.release()
    return werte


def kontaktbogen(bilder: list[Path], ziel: Path, spalten: int = 6) -> None:
    """Übersichtsbild aller Szenen-Standbilder mit Nummern."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    if not bilder:
        return
    thumbs = []
    for p in bilder:
        im = Image.open(p).convert("RGB")
        im.thumbnail((240, 427))
        thumbs.append(im)
    w = max(t.width for t in thumbs)
    h = max(t.height for t in thumbs)
    zeilen = (len(thumbs) + spalten - 1) // spalten
    bogen = Image.new("RGB", (spalten * w, zeilen * h), "black")
    try:
        from .config import FONTS_DIR
        font = ImageFont.truetype(str(FONTS_DIR / "Montserrat-Black.ttf"), 28)
    except Exception:
        font = ImageFont.load_default()
    for i, t in enumerate(thumbs):
        x, y = (i % spalten) * w, (i // spalten) * h
        bogen.paste(t, (x, y))
        d = ImageDraw.Draw(bogen)
        d.text((x + 8, y + 6), str(i + 1), fill="yellow", font=font, stroke_width=3, stroke_fill="black")
    bogen.save(ziel, quality=88)


# ---------------------------------------------------------------------------
# Transkription
# ---------------------------------------------------------------------------


def extrahiere_ton(video: Path, ziel: Path) -> None:
    run(["ffmpeg", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(ziel)])


def transkribiere(wav: Path, modell: str = "small", sprache: str | None = None) -> dict:
    """Transkribiert mit faster-whisper (bevorzugt) oder openai-whisper.

    Rückgabe: {"status", "engine", "sprache", "segmente": [{start, ende, text, woerter:[...]}]}
    """
    fehler_fw = None
    try:
        from faster_whisper import WhisperModel

        m = WhisperModel(modell, device="auto", compute_type="int8")
        segs, info = m.transcribe(str(wav), language=sprache, word_timestamps=True, vad_filter=True)
        segmente = []
        for s in segs:
            segmente.append({
                "start": round(s.start, 2), "ende": round(s.end, 2), "text": s.text.strip(),
                "woerter": [{"start": round(w.start, 2), "ende": round(w.end, 2), "wort": w.word.strip()}
                            for w in (s.words or [])],
            })
        return {"status": "ok", "engine": f"faster-whisper/{modell}", "sprache": info.language,
                "segmente": segmente}
    except ImportError:
        pass
    except Exception as e:  # z. B. Modell-Download nicht möglich
        fehler_fw = f"{type(e).__name__}: {e}"

    try:
        import whisper  # openai-whisper

        m = whisper.load_model(modell)
        r = m.transcribe(str(wav), language=sprache, word_timestamps=True)
        segmente = [{
            "start": round(s["start"], 2), "ende": round(s["end"], 2), "text": s["text"].strip(),
            "woerter": [{"start": round(w["start"], 2), "ende": round(w["end"], 2), "wort": w["word"].strip()}
                        for w in s.get("words", [])],
        } for s in r["segments"]]
        return {"status": "ok", "engine": f"openai-whisper/{modell}", "sprache": r.get("language"),
                "segmente": segmente}
    except ImportError:
        grund = "Weder faster-whisper noch openai-whisper ist installiert (pip install faster-whisper)."
    except Exception as e:
        grund = f"{type(e).__name__}: {e}"
    if fehler_fw:
        grund = f"faster-whisper: {fehler_fw}"
    return {"status": "fehlgeschlagen", "grund": grund, "segmente": []}


def ordne_dialog_zu(szenen: list[dict], segmente: list[dict]) -> None:
    """Verteilt Wörter (bzw. Segmente) anhand ihres Zeitmittelpunkts auf die Szenen."""
    for sz in szenen:
        sz["dialog"] = ""
        sz["dialog_segmente"] = []

    def szene_bei(t: float) -> dict | None:
        for sz in szenen:
            if sz["start"] <= t < sz["ende"]:
                return sz
        return szenen[-1] if szenen and t >= szenen[-1]["start"] else None

    for seg in segmente:
        woerter = seg.get("woerter") or []
        if woerter:
            gruppen: dict[int, list[dict]] = {}
            for w in woerter:
                sz = szene_bei((w["start"] + w["ende"]) / 2)
                if sz is not None:
                    gruppen.setdefault(sz["nr"], []).append(w)
            for nr, ws in gruppen.items():
                sz = szenen[nr - 1]
                text = _join_woerter([w["wort"] for w in ws])
                sz["dialog_segmente"].append({"start": ws[0]["start"], "ende": ws[-1]["ende"], "text": text})
        else:
            sz = szene_bei((seg["start"] + seg["ende"]) / 2)
            if sz is not None:
                sz["dialog_segmente"].append({"start": seg["start"], "ende": seg["ende"], "text": seg["text"]})

    for sz in szenen:
        sz["dialog"] = " ".join(s["text"] for s in sz["dialog_segmente"]).strip()


def _join_woerter(woerter: list[str]) -> str:
    text = " ".join(w for w in woerter if w)
    return re.sub(r"\s+([,.!?;:])", r"\1", text).strip()


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------


def analyze(video: Path, projekt: Projekt, schwelle: float | None = None, min_laenge: float = 0.35,
            whisper_modell: str = "small", sprache: str | None = None, ohne_ton: bool = False) -> dict:
    pruefe_ffmpeg()
    video = video.resolve()
    if not video.exists():
        raise SystemExit(f"Video nicht gefunden: {video}")

    print(f"[analyze] Video: {video.name}")
    info = video_info(video)
    print(f"[analyze] {info.get('breite')}x{info.get('hoehe')}, {info.get('fps')} fps, {info['dauer']:.2f}s, "
          f"Ton: {'ja' if info['hat_ton'] else 'nein'}")

    grenzen, methode = erkenne_szenen(video, info, schwelle, min_laenge)
    print(f"[analyze] {len(grenzen)} Szenen erkannt ({methode})")

    for alt in projekt.frames.glob("szene_*.jpg"):
        alt.unlink()
    bewegung = bewegung_pro_szene(video, grenzen)
    szenen, bilder = [], []
    for i, (start, ende) in enumerate(grenzen, start=1):
        bild = projekt.frames / f"szene_{i:03d}.jpg"
        mitte = start + (ende - start) / 2
        speichere_standbild(video, mitte, bild)
        bilder.append(bild)
        szenen.append({
            "nr": i,
            "start": start,
            "ende": ende,
            "dauer": round(ende - start, 3),
            "standbild": str(bild.relative_to(projekt.ordner)),
            "bildbeschreibung": None,  # wird im script-Schritt per Claude-Vision aus dem Standbild ergänzt
            "bild_merkmale": {**bild_merkmale(bild), "bewegung": bewegung[i - 1]},
        })
    kontaktbogen(bilder, projekt.ordner / "kontaktbogen.jpg")

    transkript = {"status": "uebersprungen", "segmente": []}
    if ohne_ton:
        print("[analyze] Transkription übersprungen (--ohne-ton)")
    elif not info["hat_ton"]:
        transkript = {"status": "kein_ton", "segmente": []}
        print("[analyze] Video hat keine Tonspur")
    else:
        wav = projekt.ordner / "ton_original.wav"
        extrahiere_ton(video, wav)
        print(f"[analyze] Transkribiere mit Whisper ({whisper_modell}) ...")
        transkript = transkribiere(wav, whisper_modell, sprache)
        if transkript["status"] == "ok":
            print(f"[analyze] {len(transkript['segmente'])} Dialogsegmente, Sprache: {transkript.get('sprache')}")
        else:
            print(f"[analyze] WARNUNG: Transkription fehlgeschlagen – {transkript.get('grund')}")
    ordne_dialog_zu(szenen, transkript["segmente"])

    dauern = [s["dauer"] for s in szenen]
    woerter = sum(len(s["dialog"].split()) for s in szenen)
    analyse = {
        "version": 1,
        "erstellt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quelle": {"datei": video.name, **info},
        "szenenerkennung": methode,
        "tempo": {
            "anzahl_szenen": len(szenen),
            "durchschnittliche_szenendauer": round(sum(dauern) / len(dauern), 2),
            "kuerzeste_szene": round(min(dauern), 2),
            "laengste_szene": round(max(dauern), 2),
            "schnitte_pro_sekunde": round((len(szenen) - 1) / info["dauer"], 2) if info["dauer"] else None,
            "woerter_pro_minute": round(woerter / info["dauer"] * 60, 1) if info["dauer"] else None,
            "szenen_mit_dialog": sum(1 for s in szenen if s["dialog"]),
        },
        "transkription": {k: v for k, v in transkript.items() if k != "segmente"},
        "transkript_volltext": " ".join(s["text"] for s in transkript["segmente"]).strip(),
        "szenen": szenen,
    }
    projekt.analysis.write_text(json.dumps(analyse, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyze] Gespeichert: {projekt.analysis}")
    return analyse

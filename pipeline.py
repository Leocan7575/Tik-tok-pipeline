#!/usr/bin/env python3
"""CLI der TikTok-KI-Video-Pipeline.

Beispiele:
    python pipeline.py analyze vorbild.mp4
    python pipeline.py assemble --projekt vorbild --musik musik.mp3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tiktok_pipeline.config import Projekt, lade_env


def _projekt(args, video: Path | None = None) -> Projekt:
    return Projekt.aus_name(getattr(args, "projekt", None), video)


def cmd_analyze(args) -> None:
    from tiktok_pipeline.analyze import analyze

    video = Path(args.video)
    analyze(video, _projekt(args, video), schwelle=args.schwelle, min_laenge=args.min_szene,
            whisper_modell=args.whisper_modell, sprache=args.sprache, ohne_ton=args.ohne_ton)


def cmd_assemble(args) -> None:
    from tiktok_pipeline.assemble import assemble

    assemble(_projekt(args), musik=Path(args.musik) if args.musik else None,
             musik_lautstaerke=args.musik_lautstaerke, clip_ton=args.clip_ton,
             untertitel=not args.ohne_untertitel, platzhalter=not args.ohne_platzhalter,
             grossbuchstaben=not args.normale_schreibung, preset=args.preset,
             lautheit=None if args.ohne_normalisierung else args.lautheit,
             ausgabe=Path(args.ausgabe) if args.ausgabe else None, neu_rendern=args.neu_rendern)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline.py", description="Vorbild-Video -> neues KI-Video (9:16)")
    sub = p.add_subparsers(dest="befehl", required=True)

    def projekt_arg(sp, video_hinweis: bool = False):
        hilfe = "Projektname oder -ordner (Standard: Dateiname des Videos)" if video_hinweis \
            else "Projektname (Ordner unter projekte/) oder Pfad"
        sp.add_argument("--projekt", "-p", help=hilfe, required=not video_hinweis)

    a = sub.add_parser("analyze", help="Szenen, Standbilder und Transkript -> analysis.json")
    a.add_argument("video", help="Vorbild-Video (.mp4/.mov)")
    projekt_arg(a, video_hinweis=True)
    a.add_argument("--schwelle", type=float, default=None,
                   help="ContentDetector-Schwelle (z. B. 27). Ohne Angabe: AdaptiveDetector")
    a.add_argument("--min-szene", type=float, default=0.35, help="Minimale Szenenlänge in s (Standard 0.35)")
    a.add_argument("--whisper-modell", default="small", help="tiny/base/small/medium/large-v3 (Standard small)")
    a.add_argument("--sprache", default=None, help="Sprache erzwingen, z. B. de oder en (Standard: automatisch)")
    a.add_argument("--ohne-ton", action="store_true", help="Keine Transkription")
    a.set_defaults(func=cmd_analyze)

    s = sub.add_parser("assemble", help="Clips + Stimmen + Untertitel + Musik -> final.mp4 (1080x1920)")
    projekt_arg(s)
    s.add_argument("--musik", help="Optionale Hintergrundmusik (wird geloopt und beim Sprechen abgesenkt)")
    s.add_argument("--musik-lautstaerke", type=float, default=0.12, help="Standard 0.12")
    s.add_argument("--clip-ton", type=float, default=0.0,
                   help="Lautstärke des Original-Tons der KI-Clips (0 = aus, z. B. 0.3)")
    s.add_argument("--ohne-untertitel", action="store_true")
    s.add_argument("--normale-schreibung", action="store_true", help="Untertitel nicht in GROSSBUCHSTABEN")
    s.add_argument("--ohne-platzhalter", action="store_true", help="Abbrechen, wenn ein Clip fehlt")
    s.add_argument("--lautheit", type=float, default=-14.0, help="Ziel-Lautheit in LUFS (Standard -14)")
    s.add_argument("--ohne-normalisierung", action="store_true")
    s.add_argument("--preset", default="medium", help="x264-Preset (ultrafast … veryslow)")
    s.add_argument("--ausgabe", "-o", help="Zieldatei (Standard: projekte/<name>/final.mp4)")
    s.add_argument("--neu-rendern", action="store_true", help="Segment-Cache ignorieren")
    s.set_defaults(func=cmd_assemble)
    return p


def main(argv: list[str] | None = None) -> None:
    lade_env()
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit("\nAbgebrochen. Bereits erzeugte Zwischenergebnisse bleiben erhalten.")
    except RuntimeError as e:
        sys.exit(f"FEHLER: {e}")


if __name__ == "__main__":
    main()

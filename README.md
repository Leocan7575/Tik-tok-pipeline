# TikTok-KI-Video-Pipeline

Aus einem viralen Vorbild-Video (.mp4/.mov) automatisch ein **neues, ähnliches KI-Video** im 9:16-Format
(1080×1920) erzeugen: gleicher Stil (3D-Animationslook, kurze Story, schnelle Schnitte, übertriebene Mimik,
Dialog), aber **eigene Story und eigene Figuren**. Figuren, Wasserzeichen oder Logos aus dem Vorbild werden
nicht kopiert – das Vorbild dient nur als Vorlage für Struktur und Tempo.

## Stand

| Schritt | Modul | Status | Kosten |
|---|---|---|---|
| 1. `analyze` – Szenen, Standbilder, Transkript | `tiktok_pipeline/analyze.py` | ✅ fertig | kostenlos (lokal) |
| 2. `script` – neue Story (Claude) | – | ⏳ folgt | API |
| 3. `characters` – Referenzbilder der Figuren | – | ⏳ folgt | API |
| 4. `generate` – Clips (Sora / Veo / Kling / Runway) | – | ⏳ folgt | API |
| 5. `voice` – Dialoge vertonen (ElevenLabs) | – | ⏳ folgt | API |
| 6. `assemble` – Schnitt, Ton, Untertitel, Musik | `tiktok_pipeline/assemble.py` | ✅ fertig | kostenlos (lokal) |

## Einrichtung

Voraussetzungen: **Python 3.10+** und **ffmpeg** (mit libass, bei den üblichen Builds dabei).

```bash
# ffmpeg
brew install ffmpeg            # macOS
sudo apt install ffmpeg        # Ubuntu/Debian
# Windows: https://www.gyan.dev/ffmpeg/builds/ und den bin-Ordner zum PATH hinzufügen

# Python-Umgebung
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# API-Schlüssel (erst für die API-Schritte nötig)
cp .env.example .env           # dann .env mit einem Editor ausfüllen
```

Beim ersten `analyze` lädt faster-whisper das Spracherkennungsmodell herunter (`small` ≈ 480 MB, einmalig).

### API-Schlüssel

Schlüssel werden **ausschließlich** aus der Datei `.env` gelesen. `.env` steht in `.gitignore` und darf nie
committet werden.

| Variable | Wofür | Woher |
|---|---|---|
| `ANTHROPIC_API_KEY` | Story/Script (Schritt 2) | console.anthropic.com |
| `OPENAI_API_KEY` | Bilder und Sora-Clips | platform.openai.com |
| `GOOGLE_API_KEY` | Veo-Clips / Imagen | aistudio.google.com |
| `KLING_ACCESS_KEY`, `KLING_SECRET_KEY` | Kling-Clips | Kling-Developer-Konsole |
| `RUNWAY_API_KEY` | Runway-Clips | dev.runwayml.com |
| `ELEVENLABS_API_KEY` | Stimmen (Schritt 5) | elevenlabs.io |

Für `analyze` und `assemble` wird **kein** Schlüssel benötigt.

## Projektordner

Jeder Durchlauf hat einen Ordner unter `projekte/<name>/` (Standardname = Dateiname des Vorbilds):

```
projekte/vorbild/
├── analysis.json        # Ergebnis von analyze
├── kontaktbogen.jpg     # Übersicht aller Szenen-Standbilder
├── frames/szene_001.jpg # ein Standbild pro Szene (Bildmitte)
├── script.json          # neue Story (Schritt 2)
├── clips/szene_001.mp4  # KI-Clips (Schritt 4)
├── voice/szene_001.mp3  # Dialoge (Schritt 5)
├── build/               # Zwischendateien von assemble (Cache)
├── final.mp4            # fertiges Video 1080×1920
└── final.srt            # Untertitel zum Hochladen
```

## Befehle

### 1. analyze

```bash
python pipeline.py analyze vorbild.mp4
python pipeline.py analyze vorbild.mp4 --projekt katzen01 --sprache de --whisper-modell medium
python pipeline.py analyze vorbild.mp4 --schwelle 27     # klassischer ContentDetector statt Adaptive
```

- Szenenwechsel mit PySceneDetect (AdaptiveDetector, robust bei schnellen Kameraschwenks;
  Fallback: ffmpeg-Szenenfilter).
- Pro Szene ein Standbild aus der Szenenmitte + Kontaktbogen.
- Lokale Bildmerkmale pro Szene: Helligkeit, Sättigung, dominante Farben, Bewegungsstärke.
- Transkription mit Whisper (Wort-Zeitstempel), Dialog wird jeder Szene zugeordnet.
- Tempo-Kennzahlen: Szenenanzahl, Ø-Szenendauer, Schnitte/Sekunde, Wörter/Minute.

Die inhaltliche `bildbeschreibung` je Szene bleibt hier noch leer und wird im `script`-Schritt per
Claude-Vision aus den Standbildern ergänzt (damit `analyze` kostenlos bleibt).

### 6. assemble

```bash
python pipeline.py assemble --projekt vorbild
python pipeline.py assemble -p vorbild --musik musik.mp3 --musik-lautstaerke 0.1
python pipeline.py assemble -p vorbild --clip-ton 0.3       # Original-Ton der KI-Clips leise mitlaufen lassen
python pipeline.py assemble -p vorbild --ohne-platzhalter   # abbrechen, falls ein Clip fehlt
```

- Clips werden auf 1080×1920 / 30 fps gebracht (Querformat wird mittig beschnitten).
- Szenenlänge kommt aus `script.json`; ist die Sprachaufnahme länger, wird die Szene verlängert
  (letztes Bild friert ein), damit kein Satz abgeschnitten wird. Zu lange Clips werden gekürzt.
- Harte Schnitte (TikTok-Stil), Stimme pro Szene, optional Clip-Ton.
- Untertitel eingebrannt: Montserrat Black, GROSSBUCHSTABEN, dicke Kontur, 2–3 Wörter pro Einblendung,
  kleine Pop-Animation, oberhalb der TikTok-Bedienelemente. Optional eigene Farbe pro Figur
  (`figuren[].untertitel_farbe` in `script.json`).
- Hintergrundmusik optional: wird geloopt, beim Sprechen automatisch abgesenkt (Ducking), am Ende ausgeblendet.
- Lautheit auf −14 LUFS normalisiert (TikTok-üblich), H.264/AAC, `+faststart`.
- **Platzhalter:** Fehlt ein Clip, wird eine Tafel mit Szenennummer, Prompt und Dialog gerendert. So lässt sich
  das Timing (Animatic) prüfen, bevor Geld für Videogenerierung ausgegeben wird.
- **Cache:** Jede Szene wird als eigenes Segment gerendert und nur neu gebaut, wenn sich Clip, Stimme oder Dauer
  geändert haben – nach dem Neu-Erzeugen einer einzelnen Szene geht der Schnitt in Sekunden.

### drehbuch

```bash
python pipeline.py drehbuch --projekt mops
```

Setzt die Video-Prompts aller Szenen neu zusammen (Stil + **wortgleiche Figurenbeschreibung** + Kamera + Handlung)
und exportiert `drehbuch.md` mit Ablauftabelle und Prompts zum Kopieren in Web-Apps (Kling, Hailuo, …).

Beispiel: `beispiele/mops/` – „Bruno muss in die Wanne“ (53 Szenen, 67 s, Dramaturgie und Tempo wie das Vorbild).
Zum Ausprobieren: `mkdir -p projekte/mops && cp beispiele/mops/script.json projekte/mops/ && python pipeline.py assemble -p mops`

### script.json-Format (wird von Schritt 2 erzeugt, kann auch von Hand geschrieben werden)

```json
{
  "titel": "Der verschwundene Käse",
  "stil": "Stylized 3D animated feature-film look, ...",
  "figuren": [
    {"id": "fuchs", "name": "Fritz", "beschreibung": "a slim red fox with ...", "untertitel_farbe": "#FFE14D"}
  ],
  "szenen": [
    {"nr": 1, "dauer": 1.6, "kamera": "Close-up", "figuren_im_bild": ["fuchs"],
     "aktion": "Fritz stares at an empty plate in shock ...", "beschreibung_de": "Fritz entdeckt den leeren Teller",
     "sprecher": "fuchs", "dialog": "Moment mal, wo ist mein Käse?!", "einblendung": "",
     "prompt": "(wird von 'drehbuch' automatisch erzeugt)"}
  ]
}
```

`einblendung` blendet einen großen Comic-Text (z. B. „HAB DICH!“) über die ganze Szene ein – per ffmpeg,
weil KI-Videomodelle Schrift oft fehlerhaft darstellen.

Dateien werden über die Szenennummer gefunden: `clips/szene_001.mp4`, `voice/szene_001.mp3` (auch .wav/.m4a).

## Geplante Befehle (API-Schritte)

```bash
python pipeline.py run vorbild.mp4 --thema "..." --anbieter sora      # alles in einem Durchlauf
python pipeline.py run vorbild.mp4 --thema "..." --dry-run            # ohne kostenpflichtige Aufrufe
python pipeline.py regenerate --projekt vorbild --szene 7             # einzelne Szene neu erzeugen
```

Vor jedem kostenpflichtigen Schritt wird eine Kostenschätzung angezeigt und auf Bestätigung gewartet.

## Tests

```bash
python -m pytest tests/
python tests/make_test_video.py testvideo.mp4    # synthetisches Testvideo mit 6 harten Schnitten
python pipeline.py analyze testvideo.mp4 --projekt test
```

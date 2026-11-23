"""Prompts aus script.json zusammensetzen und ein lesbares Drehbuch (Markdown) exportieren.

Jede Szene in script.json enthält nur ihre eigene Handlung ("aktion") und welche Figuren im Bild sind.
Der vollständige Video-Prompt wird hier immer gleich aufgebaut:

    <Stil> + <feste Beschreibung jeder Figur im Bild, wortgleich> + <Kamera> + <Handlung> + <Regeln>

So bleiben Figuren und Look über alle Clips konsistent.
"""
from __future__ import annotations

import json

from .config import Projekt

STANDARD_REGELN = (
    "Exaggerated, highly expressive cartoon facial expressions. The main action starts immediately "
    "in the first second. Vertical 9:16 framing. No text, no captions, no watermark, no logo."
)


def baue_prompt(script: dict, szene: dict) -> str:
    figuren = {f["id"]: f for f in script.get("figuren", [])}
    teile = [script.get("stil", "").strip()]
    for fid in szene.get("figuren_im_bild", []):
        f = figuren.get(fid)
        if f:
            teile.append(f"{f['name']}: {f['beschreibung'].strip()}")
    if szene.get("kamera"):
        teile.append(f"Camera: {szene['kamera']}.")
    teile.append(szene.get("aktion", "").strip())
    teile.append(script.get("regeln", STANDARD_REGELN).strip())
    return " ".join(t if t.endswith((".", "!", "?")) else t + "." for t in teile if t)


def fuelle_prompts(projekt: Projekt) -> dict:
    script = json.loads(projekt.script.read_text(encoding="utf-8"))
    for sz in script["szenen"]:
        if sz.get("aktion"):
            sz["prompt"] = baue_prompt(script, sz)
    projekt.script.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    return script


def schreibe_markdown(projekt: Projekt) -> None:
    script = fuelle_prompts(projekt)
    sz_liste = script["szenen"]
    gesamt = sum(float(s.get("dauer", 0)) for s in sz_liste)
    z = [f"# {script.get('titel', 'Drehbuch')}", ""]
    if script.get("logline"):
        z += [f"_{script['logline']}_", ""]
    z += [f"**{len(sz_liste)} Szenen · ca. {gesamt:.0f} s · 1080×1920**", ""]
    z += ["## Figuren (feste Beschreibung – steckt wortgleich in jedem Prompt)", ""]
    for f in script.get("figuren", []):
        z += [f"- **{f['name']}** (`{f['id']}`): {f['beschreibung']}"]
        if f.get("stimme"):
            z += [f"  - Stimme: {f['stimme']}"]
    z += ["", "## Stil", "", script.get("stil", ""), ""]
    z += ["## Ablauf", "", "| Nr | Akt | Dauer | Kamera | Was passiert | Dialog / Einblendung |",
          "|---|---|---|---|---|---|"]
    for s in sz_liste:
        dialog = ""
        if s.get("dialog"):
            dialog = f"**{s.get('sprecher', '')}:** „{s['dialog']}“"
        if s.get("einblendung"):
            dialog += f" 💥 {s['einblendung']}"
        z += [f"| {s['nr']} | {s.get('akt', '')} | {s['dauer']} s | {s.get('kamera', '')} | "
              f"{s.get('beschreibung_de', '')} | {dialog} |"]
    z += ["", "## Prompts zum Kopieren", "",
          "Clips in der Web-App mit 5 s Länge erzeugen und als `clips/szene_XXX.mp4` speichern – "
          "die Pipeline kürzt automatisch auf die Szenendauer (die Handlung steht deshalb am Anfang).", ""]
    for s in sz_liste:
        z += [f"### Szene {s['nr']} · {s['dauer']} s · {s.get('kamera', '')}", "", "```", s.get("prompt", ""), "```", ""]
    (projekt.ordner / "drehbuch.md").write_text("\n".join(z), encoding="utf-8")
    print(f"[drehbuch] Prompts aktualisiert und Drehbuch geschrieben: {projekt.ordner / 'drehbuch.md'}")

"""Schnelle Tests ohne Video/Netz: python -m pytest tests/"""
from tiktok_pipeline.analyze import ordne_dialog_zu
from tiktok_pipeline.subtitles import Stil, wortgruppen, zeilen_fuer_dialog


def _szenen():
    return [{"nr": 1, "start": 0.0, "ende": 2.0}, {"nr": 2, "start": 2.0, "ende": 4.0},
            {"nr": 3, "start": 4.0, "ende": 5.0}]


def test_woerter_werden_ueber_schnitt_verteilt():
    seg = {"start": 1.2, "ende": 2.8, "text": "Wo ist mein Käse?", "woerter": [
        {"start": 1.2, "ende": 1.4, "wort": "Wo"}, {"start": 1.5, "ende": 1.8, "wort": "ist"},
        {"start": 2.1, "ende": 2.4, "wort": "mein"}, {"start": 2.4, "ende": 2.8, "wort": "Käse?"}]}
    sz = _szenen()
    ordne_dialog_zu(sz, [seg])
    assert sz[0]["dialog"] == "Wo ist"
    assert sz[1]["dialog"] == "mein Käse?"
    assert sz[2]["dialog"] == ""


def test_segment_ohne_woerter_nach_mittelpunkt():
    sz = _szenen()
    ordne_dialog_zu(sz, [{"start": 4.1, "ende": 4.9, "text": "Hallo!", "woerter": []}])
    assert sz[2]["dialog"] == "Hallo!"


def test_wortgruppen_kurz_und_satzende():
    g = wortgruppen("Moment mal, wo ist mein Käse?! Frag den Waschbären.", 3, 16)
    assert all(len(x.split()) <= 3 for x in g)
    assert "Käse?!" in g[1] and g[1].endswith("Käse?!")


def test_zeilen_decken_zeitraum_ab():
    z = zeilen_fuer_dialog("Eins zwei drei vier fünf sechs", 1.0, 3.0, Stil())
    assert abs(z[0].start - 1.0) < 1e-6 and abs(z[-1].ende - 3.0) < 1e-6
    assert all(a.ende == b.start for a, b in zip(z, z[1:]))

"""
Einen hochgeladenen Geschäftsbericht auswerten: Gemini liest einen festen Satz
von 9 Kennzahlen (mit Seite und wörtlichem Zitat), daraus werden die
Modellparameter abgeleitet. Nutzt die Funktionen aus src/ki_extraktion.py.
"""
import hashlib
import json
import os
import re
import time

from src import ki_extraktion as ki

PAUSE = 5   # Sekunden zwischen Anfragen (Free-Tier-Limit)

# Dasselbe Ziel in allen drei Zielfragen, damit die KI nicht drei verschiedene Ziele mischt
ZIEL = ("das wichtigste kurzfristige Emissionsreduktionsziel des Konzerns "
        "(bevorzugt absolute Scope-1- und Scope-2-Emissionen, sonst die Emissionsintensität)")
ZIEL_SUCHE = ["Reduktionsziel", "Ziel", "Scope 1 und 2", "Intensität", "2030"]

# (Schlüssel, Frage an die KI, Suchbegriffe für die Seitenauswahl)
KENNZAHLEN = [
    ("ebit", "Bereinigtes EBIT bzw. operatives Ergebnis vor Sondereffekten (Mio. €)",
     ["bereinigtes EBIT", "Adjusted EBIT", "operatives Ergebnis", "EBIT"]),
    ("steuersatz", "Erwarteter Konzernsteuersatz; falls nicht angegeben: effektive Steuerquote (%)",
     ["Steuersatz", "Steuerquote", "tax rate"]),
    ("wacc", "Kapitalkostensatz (WACC) NACH Steuern aus dem jüngsten Werthaltigkeitstest (%)",
     ["nach Steuern", "Kapitalkosten", "WACC", "Werthaltigkeit"]),
    ("nettofinanzschulden", "Nettofinanzschulden zum Bilanzstichtag (Mio. €); bei einem "
     "Netto-Finanzguthaben (mehr Liquidität als Finanzschulden) als NEGATIVE Zahl",
     ["Nettofinanzschulden", "Netto-Finanzschulden", "Netto-Finanzguthaben", "Nettoverschuldung"]),
    ("pensionen", "Rückstellungen für Pensionen und ähnliche Verpflichtungen zum Bilanzstichtag (Mio. €)",
     ["Rückstellungen für Pensionen", "Pensionsrückstellungen", "Pensionen"]),
    ("scope1", "Scope-1-THG-Bruttoemissionen des Konzerns (Mio. t CO2e)",
     ["Scope-1", "Scope 1", "THG-Bruttoemissionen"]),
    ("ziel_aktuell", f"Wert im Berichtsjahr für {ZIEL} (in der Einheit des Ziels)", ZIEL_SUCHE),
    ("ziel_wert", f"Zielwert für {ZIEL} (in der Einheit des Ziels)", ZIEL_SUCHE),
    ("ziel_jahr", f"Zieljahr für {ZIEL} (vierstellige Jahreszahl)", ZIEL_SUCHE),
]


def kurzname(text):
    """'Thyssenkrupp AG' -> 'thyssenkrupp_ag' (für Dateinamen)."""
    text = text.lower()
    for alt, neu in {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}.items():
        text = text.replace(alt, neu)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def kennung(inhalt):
    """Fingerabdruck der PDF-Datei: gleicher Bericht = gleiche Kennung = keine neue KI-Anfrage."""
    return hashlib.md5(inhalt).hexdigest()[:10]


def ergebnis_pfad(kenn):
    return f"data/processed/kennzahlen_{kenn}.json"


def zitat_belegt(antwort, seiten):
    """Steht das Zitat wörtlich auf der genannten Seite? (wie in ki_extraktion.pruefe)"""
    zitat = ki.ohne_leerzeichen(antwort.zitat)
    return (antwort.seite is not None and 1 <= antwort.seite <= len(seiten)
            and len(zitat) >= 5 and any(z.isdigit() for z in zitat)
            and zitat in ki.ohne_leerzeichen(seiten[antwort.seite - 1]))


def auswerten(pdf_pfad, kenn, name, geschaeftsjahr, fortschritt=None):
    """Fragt die KI nach allen Kennzahlen. Liegt schon ein Ergebnis vor, wird es
    nur geladen – dann gibt es keine einzige Anfrage an Gemini."""
    pfad = ergebnis_pfad(kenn)
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)

    bericht = {"name": name, "geschaeftsjahr": geschaeftsjahr, "pdf": pdf_pfad,
               "cache": f"data/processed/seiten_{kenn}.json"}
    seiten = ki.seiten_laden(bericht)
    client = ki.genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    zeilen = []
    for i, (schluessel, frage, suchbegriffe) in enumerate(KENNZAHLEN):
        try:
            antwort = ki.frage_ki(client, bericht, frage, seiten,
                                  ki.passende_seiten(seiten, suchbegriffe))
            zeilen.append({"schluessel": schluessel, "Kennzahl": frage, "KI-Wert": antwort.wert,
                           "Seite": antwort.seite, "Zitat belegt": zitat_belegt(antwort, seiten),
                           "Zitat": antwort.zitat})
        except Exception as fehler:   # eine fehlgeschlagene Frage soll nicht alles abbrechen
            zeilen.append({"schluessel": schluessel, "Kennzahl": frage, "KI-Wert": None,
                           "Seite": None, "Zitat belegt": False, "Zitat": f"Fehler: {fehler}"})
        if fortschritt:
            fortschritt((i + 1) / len(KENNZAHLEN), frage)
        if i < len(KENNZAHLEN) - 1:
            time.sleep(PAUSE)

    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(zeilen, f, ensure_ascii=False, indent=1)
    return zeilen


def berichtsjahr(geschaeftsjahr):
    """'2024/2025' -> 2025, '2025' -> 2025 (letzte vierstellige Jahreszahl)."""
    jahre = re.findall(r"\d{4}", geschaeftsjahr)
    return int(jahre[-1]) if jahre else 2025


def reduktion_pro_jahr(aktuell, ziel, zieljahr, jahr):
    """Gleichmäßige jährliche Reduktion, um vom aktuellen Wert zum Ziel zu kommen."""
    if not aktuell or not ziel or not zieljahr or zieljahr <= jahr or ziel >= aktuell:
        return 0.0
    return 1 - (ziel / aktuell) ** (1 / (zieljahr - jahr))

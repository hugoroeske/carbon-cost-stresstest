"""
KI-Extraktion: Gemini liest Kennzahlen aus einem Geschäftsbericht –
mit Seitenzahl und wörtlichem Zitat als Prüfspur.
Danach prüft das Skript jede Antwort automatisch gegen annahmen.md.

Aufruf im Terminal:  python src/ki_extraktion.py heidelberg
                     python src/ki_extraktion.py thyssenkrupp
"""
import json
import os
import re
import sys
import time

import pandas as pd
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field
from pypdf import PdfReader

load_dotenv()
MODELL = "gemini-3.8-flash"
SEITEN_PRO_FRAGE = 8                   # so viele passende Seiten bekommt die KI
PAUSE = 5                              # Sekunden zwischen Anfragen (Free-Tier-Limit)

# --- Je Bericht: Datei, Geschäftsjahr und die gesuchten Kennzahlen -------
# Kennzahl: (Suchbegriffe, Referenzwert aus annahmen.md = von Hand geprüft)
BERICHTE = {
    "heidelberg": {
        "name": "Heidelberg Materials",
        "geschaeftsjahr": "2025",
        "pdf": "data/raw/HM_GNB25_de.pdf",
        "cache": "data/processed/seiten_HM_GNB25.json",
        "ergebnis": "ergebnisse/ki_extraktion_heidelberg.csv",
        "kennzahlen": {
            "Umsatz 2025 (Mio. €)":
                (["Umsatzerlöse", "Revenue"], 21460),
            "Operatives Ergebnis VOR Sondereffekten 2025 (Mio. €), also bereinigtes EBIT; "
            "bei Heidelberg 'Ergebnis des laufenden Geschäftsbetriebs (RCO)'":
                (["Ergebnis des laufenden Geschäftsbetriebs", "bereinigt", "adjusted EBIT"], 3381),
            "Abschreibungen 2025 (Mio. €)":
                (["Abschreibungen", "Depreciation"], 1298),
            "Effektive Steuerquote 2025 (%)":
                (["Steuerquote", "tax rate"], 25.2),
            "Free Cashflow 2025 (Mio. €)":
                (["Free Cashflow", "free cash flow"], 2109),
            "Nettofinanzschulden 31.12.2025 (Mio. €)":
                (["Nettofinanzschulden", "net debt"], 5715),
            "Absolute Brutto-Scope-1-Emissionen Konzern 2025 (Mio. t CO2e)":
                (["Scope-1", "Scope 1"], 61.3),
        },
    },
    "thyssenkrupp": {
        "name": "Thyssenkrupp",
        "geschaeftsjahr": "2024/2025 (1.10.2024 bis 30.9.2025)",
        "pdf": "data/raw/Thyssenkrupp_2025.pdf",
        "cache": "data/processed/seiten_Thyssenkrupp_2025.json",
        "ergebnis": "ergebnisse/ki_extraktion_thyssenkrupp.csv",
        "kennzahlen": {
            "Umsatz 2024/2025 (Mio. €)":
                (["Umsatzerlöse", "Umsatz"], 32837),
            "Bereinigtes EBIT 2024/2025 (Mio. €)":
                (["Bereinigtes EBIT", "EBIT bereinigt"], 640),
            "Free Cashflow vor M&A 2024/2025 (Mio. €)":
                (["Free Cashflow vor M&A", "FCF vor M&A"], 363),
            "Netto-Finanzguthaben zum 30.9.2025 (Mio. €)":
                (["Netto-Finanzguthaben", "Netto-Finanzschulden"], 4862),
            "Rückstellungen für Pensionen zum 30.9.2025 (Mio. €)":
                (["Rückstellungen für Pensionen", "Pensionen"], 5298),
            "Scope-1-THG-Bruttoemissionen Konzern 2024/2025 (Mio. t CO2e)":
                (["Scope-1-THG-Bruttoemissionen", "Scope 1"], 19.8),
            "Kapitalkostensatz nach Steuern im Werthaltigkeitstest Steel Europe "
            "im 4. Quartal 2024/2025 (%)":
                (["Kapitalkostensatz (nach Steuern)", "Steel Europe", "Werthaltigkeitstest"], 7.6),
        },
    },
}


# --- Antwortformat, das die KI ausfüllen MUSS ----------------------------
class Antwort(BaseModel):
    wert: float | None = Field(description="Der Zahlenwert in der gefragten Einheit, ohne Tausenderpunkte. null, wenn nicht gefunden.")
    seite: int | None = Field(description="Seitennummer aus der Markierung === SEITE n ===, auf der der Wert steht.")
    zitat: str = Field(description="Wörtlicher, kurzer Textausschnitt von dieser Seite, der den Wert enthält.")


# --- 1. PDF einmal in Text umwandeln und zwischenspeichern ---------------
def seiten_laden(bericht):
    if os.path.exists(bericht["cache"]):
        with open(bericht["cache"], encoding="utf-8") as f:
            return json.load(f)
    print("Lese PDF ein (einmalig, ca. 30 Sekunden) ...")
    seiten = [seite.extract_text() or "" for seite in PdfReader(bericht["pdf"]).pages]
    os.makedirs(os.path.dirname(bericht["cache"]), exist_ok=True)
    with open(bericht["cache"], "w", encoding="utf-8") as f:
        json.dump(seiten, f, ensure_ascii=False)
    return seiten


# --- 2. Passende Seiten finden (einfaches "Retrieval") -------------------
def passende_seiten(seiten, suchbegriffe):
    """Zählt Treffer je Seite und gibt die besten Seitennummern zurück (ab 1)."""
    punkte = []
    for nr, text in enumerate(seiten, start=1):
        treffer = sum(text.lower().count(b.lower()) for b in suchbegriffe)
        if treffer > 0:
            punkte.append((treffer, nr))
    punkte.sort(reverse=True)
    return [nr for _, nr in punkte[:SEITEN_PRO_FRAGE]]


# --- 3. Die KI fragen ----------------------------------------------------
def frage_ki(client, bericht, kennzahl, seiten, seitennummern):
    kontext = "\n\n".join(f"=== SEITE {nr} ===\n{seiten[nr - 1]}" for nr in seitennummern)
    prompt = (
        "Du bist Wirtschaftsprüfer. Finde im folgenden Auszug aus dem Geschäftsbericht "
        f"von {bericht['name']} genau diese Kennzahl: {kennzahl}.\n"
        f"Regeln: Nimm den Wert für das Geschäftsjahr {bericht['geschaeftsjahr']}, nicht das Vorjahr, "
        "und – sofern die Kennzahl nichts anderes sagt – den Wert für den Gesamtkonzern. "
        "Gib die Seitenzahl aus der Markierung === SEITE n === an und ein wörtliches Zitat "
        "von genau dieser Seite. Erfinde nichts: Wenn der Wert nicht im Text steht, "
        "setze wert und seite auf null.\n\n" + kontext
    )
    antwort = client.interactions.create(
        model=MODELL,
        input=prompt,
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": Antwort.model_json_schema()},
    )
    return Antwort.model_validate_json(antwort.output_text)


# --- 4. Automatische Prüfung ---------------------------------------------
def ohne_leerzeichen(text):
    return re.sub(r"\s+", "", text.replace("\u00ad", ""))


def pruefe(antwort, referenz, seiten):
    wert_ok = antwort.wert is not None and abs(abs(antwort.wert) - abs(referenz)) <= 0.01 * abs(referenz)
    zitat = ohne_leerzeichen(antwort.zitat)
    zitat_ok = (antwort.seite is not None and 1 <= antwort.seite <= len(seiten)
                and len(zitat) >= 5 and any(z.isdigit() for z in zitat)
                and zitat in ohne_leerzeichen(seiten[antwort.seite - 1]))
    return wert_ok, zitat_ok


# --- 5. Alles zusammen ---------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in BERICHTE:
        sys.exit(f"Bitte Bericht angeben, z. B.: python src/ki_extraktion.py thyssenkrupp "
                 f"(möglich: {', '.join(BERICHTE)})")
    bericht = BERICHTE[sys.argv[1]]

    seiten = seiten_laden(bericht)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    zeilen = []
    for kennzahl, (suchbegriffe, referenz) in bericht["kennzahlen"].items():
        nummern = passende_seiten(seiten, suchbegriffe)
        antwort = frage_ki(client, bericht, kennzahl, seiten, nummern)
        wert_ok, zitat_ok = pruefe(antwort, referenz, seiten)
        zeilen.append([kennzahl, referenz, antwort.wert, antwort.seite,
                       "✅" if wert_ok else "❌", "✅" if zitat_ok else "❌", antwort.zitat])
        print(f"{'✅' if wert_ok else '❌'} {kennzahl}: KI {antwort.wert} (S. {antwort.seite}) – Referenz {referenz}")
        time.sleep(PAUSE)

    ergebnis = pd.DataFrame(zeilen, columns=["Kennzahl", "Referenz", "KI-Wert", "Seite",
                                             "Wert korrekt", "Zitat belegt", "Zitat"])
    os.makedirs("ergebnisse", exist_ok=True)
    ergebnis.to_csv(bericht["ergebnis"], index=False)

    richtig = (ergebnis["Wert korrekt"] == "✅").sum()
    belegt = (ergebnis["Zitat belegt"] == "✅").sum()
    print(f"\nGenauigkeit: {richtig} von {len(ergebnis)} Kennzahlen korrekt")
    print(f"Prüfspur:    {belegt} von {len(ergebnis)} Zitaten wörtlich auf der genannten Seite")
    print(f"Gespeichert: {bericht['ergebnis']}")
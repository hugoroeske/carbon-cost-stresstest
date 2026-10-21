"""
Upload-Seite: Geschäftsbericht per Drag & Drop hochladen, Kennzahlen per KI lesen,
von Hand prüfen, EU-ETS-Anlagen zuordnen und als neuen Konzern speichern.
"""
import datetime
import json
import os

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Analyse a report", page_icon="📄", layout="wide")
st.title("Analyse an annual report")

# Diese Seite braucht den KI-Schlüssel (.env) und das EU-Register (data/raw/). Beides liegt
# bewusst NICHT im Repository – online (Streamlit Cloud) wird die Seite deshalb abgeschaltet.
LOKAL = os.path.exists("data/raw/ets_2025.xlsx") and (
    os.path.exists(".env") or bool(os.environ.get("GEMINI_API_KEY")))
if not LOKAL:
    st.info("The upload page only runs locally on the author's computer: it uses a personal "
            "AI key and the EU emissions registry as a local file.")
    st.stop()

from src import bericht_auswertung as ba   # noqa: E402 – erst nach der Prüfung laden
from src.ets_suche import anlagen_suchen, register_laden, zusammenfassen   # noqa: E402
from src.modell import KONZERN_ORDNER   # noqa: E402

st.warning("**Upload public annual reports only.** "
           "The text is sent to the free Gemini API.")

# ---------- 1. Bericht und Stammdaten ----------
st.header("1. Upload report")
datei = st.file_uploader("Drag the annual report (PDF) here", type="pdf")

spalte1, spalte2, spalte3 = st.columns(3)
name = spalte1.text_input("Company name", placeholder="e.g. Salzgitter")
geschaeftsjahr = spalte2.text_input("Fiscal year", placeholder="e.g. 2025 or 2024/2025")
pruefer = spalte3.text_input("Statutory auditor", placeholder="e.g. KPMG")
if any(w in pruefer.lower() for w in ["pwc", "pricewaterhouse"]):
    st.error("PwC is the auditor: do not publish this company. "
             "After saving, move the file from konzerne/ to lokal/ (not in the repository).")

spalte1, spalte2, spalte3 = st.columns(3)
boersenwert = spalte1.number_input("Market capitalisation (€m)", min_value=0.0, step=100.0)
kurs_datum = spalte2.date_input("Share price date", value=datetime.date.today())
kurs_quelle = spalte3.text_input("Share price source", placeholder="e.g. onvista, Xetra close")

if datei is None:
    st.stop()   # ohne Bericht gibt es nichts weiter anzuzeigen

inhalt = datei.getvalue()
kenn = ba.kennung(inhalt)
os.makedirs("data/raw/uploads", exist_ok=True)
pdf_pfad = f"data/raw/uploads/{kenn}_{os.path.basename(datei.name)}"
if not os.path.exists(pdf_pfad):
    with open(pdf_pfad, "wb") as f:
        f.write(inhalt)

# ---------- 2. KI-Auswertung (nur nach Klick) ----------
st.header("2. Extract figures with AI")
schon_da = os.path.exists(ba.ergebnis_pfad(kenn))
if schon_da and st.session_state.get("kenn") != kenn:
    st.session_state["kennzahlen"] = ba.auswerten(pdf_pfad, kenn, name, geschaeftsjahr)  # nur laden
    st.session_state["kenn"] = kenn

if schon_da:
    st.success("This report has already been analysed – no new AI request is made.")
else:
    st.write(f"{len(ba.KENNZAHLEN)} requests to Gemini, {ba.PAUSE} seconds apart (about 1 minute).")
    if st.button("Start AI extraction", type="primary", disabled=not (name and geschaeftsjahr)):
        balken = st.progress(0.0, text="Reading PDF …")
        st.session_state["kennzahlen"] = ba.auswerten(
            pdf_pfad, kenn, name, geschaeftsjahr,
            fortschritt=lambda anteil, frage: balken.progress(anteil, text=f"Done: {frage[:60]} …"))
        st.session_state["kenn"] = kenn
        st.rerun()
    if not (name and geschaeftsjahr):
        st.caption("Please enter company name and fiscal year first.")

if st.session_state.get("kenn") != kenn:
    st.stop()

# ---------- 3. Vier-Augen-Prüfung ----------
st.header("3. Verify values manually")
st.write("Open the report on the given page and compare. Only the column "
         "**Geprüfter Wert** (verified value) can be edited.")
tabelle = pd.DataFrame(st.session_state["kennzahlen"])
tabelle["Geprüfter Wert"] = tabelle["KI-Wert"]
tabelle["Zitat belegt"] = tabelle["Zitat belegt"].map({True: "✅", False: "❌"})
geprueft = st.data_editor(
    tabelle[["Kennzahl", "KI-Wert", "Geprüfter Wert", "Seite", "Zitat belegt", "Zitat"]],
    disabled=["Kennzahl", "KI-Wert", "Seite", "Zitat belegt", "Zitat"],
    hide_index=True, key=f"pruefung_{kenn}")
werte = dict(zip(tabelle["schluessel"], geprueft["Geprüfter Wert"]))


def zahl(schluessel, standard=0.0):
    wert = werte.get(schluessel)
    return standard if wert is None or pd.isna(wert) else float(wert)


def begrenzt(wert, unten, oben):
    """Startwert in den erlaubten Bereich holen (sonst bricht number_input ab)."""
    return min(max(wert, unten), oben)


# ---------- 4. EU-ETS-Anlagen zuordnen ----------
st.header("4. Match EU ETS installations")


@st.cache_data
def register():
    return register_laden()


begriffe = st.text_input("Search terms, comma-separated (company, subsidiaries, sites)",
                         value=name)
kandidaten = anlagen_suchen(register(), begriffe.split(",")) if begriffe.strip() else None
ets = None
if kandidaten is not None:
    st.caption(f"{len(kandidaten)} matches. Tick only installations that really belong to the company "
               "(column Aufnehmen); adjust the share (Anteil) for joint ventures, e.g. 0.5.")
    auswahl = st.data_editor(kandidaten, hide_index=True, key=f"ets_{kenn}_{begriffe}",
                             disabled=[s for s in kandidaten.columns
                                       if s not in ("Aufnehmen", "Anteil", "Standort")])
    ets = zusammenfassen(auswahl, zahl("scope1") or None)
    a, b, c, d = st.columns(4)
    a.metric("Emissions 2025", f"{ets['emissionen_2025']:.2f} Mt")
    b.metric("Free allocation 2025", f"{ets['zuteilung_2025']:.2f} Mt")
    c.metric("Coverage", f"{ets['deckungsgrad']:.0%}" if ets["deckungsgrad"] else "–")
    if ets["anzahl"] and ets["abweichung_2025"] is not None:
        d.metric("Reconciliation with Scope 1", f"{ets['abweichung_2025']:+.1f} % (2025)",
                 f"{ets['abweichung_2024']:+.1f} % (2024)", delta_color="off")
    st.caption("ETS figures are per calendar year. If the fiscal year differs, the 2024 reconciliation "
               "is also meaningful. Large gaps = installations missing or too many.")

# ---------- 5. Modellparameter ----------
st.header("5. Model parameters")
jahr = ba.berichtsjahr(geschaeftsjahr)
scope1 = zahl("scope1")
ets_e = ets["emissionen_2025"] if ets and ets["anzahl"] else 0.0
bepreist_vorschlag = min(ets_e / scope1, 1.0) if scope1 and ets_e else 1.0
st.caption("Suggestions from AI and ETS – all editable. Priced emissions = Scope 1 × priced share.")

spalte1, spalte2, spalte3 = st.columns(3)
anteil_bepreist = spalte1.number_input("Priced share (ETS / Scope 1)", 0.0, 1.0,
                                       begrenzt(round(bepreist_vorschlag, 3), 0.0, 1.0), step=0.01)
emissionen = spalte2.number_input("Priced emissions 2025 (Mt)", 0.0, None,
                                  max(round(scope1 * anteil_bepreist, 3), 0.0), step=0.1)
deckungsgrad = spalte3.number_input("Free allocation coverage", 0.0, 3.0,
                                    begrenzt(round(ets["deckungsgrad"], 3), 0.0, 3.0)
                                    if ets and ets["deckungsgrad"] else 1.0, step=0.01)
reduktion = spalte1.number_input(
    "Annual reduction until 2030", 0.0, 0.5,
    begrenzt(round(ba.reduktion_pro_jahr(zahl("ziel_aktuell"), zahl("ziel_wert"),
                                         zahl("ziel_jahr"), jahr), 4), 0.0, 0.5),
    step=0.005, format="%.4f",
    help="From climate target: 1 − (target / current)^(1 / years). Only an approximation for intensity targets.")
steuersatz = spalte2.number_input("Tax rate", 0.0, 0.6,
                                  begrenzt(round(zahl("steuersatz", 30) / 100, 4), 0.0, 0.6), step=0.005)
wacc = spalte3.number_input("WACC after tax", 0.01, 0.2,
                            begrenzt(round(zahl("wacc", 8) / 100, 4), 0.01, 0.2), step=0.001)
spalte1.metric("Enterprise value (€m)",
               f"{boersenwert + zahl('nettofinanzschulden') + zahl('pensionen'):,.0f}")

# ---------- 6. Speichern ----------
st.header("6. Save company")
alle_geprueft = st.checkbox("All values verified (four-eyes principle: checked in the report)")
fehlt = [t for t, ok in [("company name", name), ("fiscal year", geschaeftsjahr),
                         ("market capitalisation", boersenwert > 0), ("share price source", kurs_quelle)] if not ok]
if fehlt:
    st.caption("Still missing: " + ", ".join(fehlt))

if st.button("Save company", type="primary", disabled=not alle_geprueft or bool(fehlt)):
    kurz = ba.kurzname(name)
    os.makedirs(KONZERN_ORDNER, exist_ok=True)
    zeile = {z["schluessel"]: z for z in st.session_state["kennzahlen"]}

    def aus_bericht(schluessel, wert):
        return {"wert": wert, "quelle": f"Geschäftsbericht {geschaeftsjahr}",
                "seite": zeile[schluessel]["Seite"], "zitat": zeile[schluessel]["Zitat"]}

    ets_text = f"EU-ETS 2025, {ets['anzahl']} Anlagen" if ets else "keine ETS-Zuordnung"
    parameter = {
        "emissionen_2025": {"wert": emissionen, "quelle": f"Scope 1 × bepreister Anteil ({ets_text})"},
        "reduktion_bis_2030": {"wert": reduktion, "quelle": "aus Klimaziel abgeleitet (Seiten siehe Prüfspur)"},
        "deckungsgrad": {"wert": deckungsgrad, "quelle": ets_text},
        "steuersatz": aus_bericht("steuersatz", steuersatz),
        "wacc": aus_bericht("wacc", wacc),
        "rco_2025": aus_bericht("ebit", zahl("ebit")),
        "boersenwert": {"wert": boersenwert, "quelle": f"{kurs_quelle}, {kurs_datum:%d.%m.%Y}"},
        "nettofinanzschulden": aus_bericht("nettofinanzschulden", zahl("nettofinanzschulden")),
        "pensionen": aus_bericht("pensionen", zahl("pensionen")),
    }
    pruefspur_pfad = f"konzerne/{kurz}_pruefspur.csv"
    spur = geprueft.copy()
    spur["Korrigiert"] = ["✏️" if a != b and not (pd.isna(a) and pd.isna(b)) else ""
                          for a, b in zip(spur["KI-Wert"], spur["Geprüfter Wert"])]
    spur.to_csv(os.path.join(KONZERN_ORDNER, f"{kurz}_pruefspur.csv"), index=False)

    gewaehlt = auswahl[auswahl["Aufnehmen"]].to_dict("records") if kandidaten is not None else []
    daten = {"name": name, "geschaeftsjahr": geschaeftsjahr, "abschlusspruefer": pruefer,
             "gespeichert": f"{datetime.date.today():%d.%m.%Y}", "bericht": os.path.basename(datei.name),
             "scope1": scope1, "anteil_bepreist": anteil_bepreist,
             "parameter": parameter, "ets_anlagen": gewaehlt, "pruefspur": pruefspur_pfad}
    with open(os.path.join(KONZERN_ORDNER, f"{kurz}.json"), "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=1, default=str)
    st.cache_data.clear()   # Monte Carlo und Tornado neu rechnen lassen
    st.success(f"Saved: konzerne/{kurz}.json – now selectable on the main page under “Company”.")

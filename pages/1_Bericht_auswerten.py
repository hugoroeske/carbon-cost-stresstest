"""
Upload-Seite: Geschäftsbericht per Drag & Drop hochladen, Kennzahlen per KI lesen,
von Hand prüfen, EU-ETS-Anlagen zuordnen und als neuen Konzern speichern.
"""
import datetime
import json
import os

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Bericht auswerten", page_icon="📄", layout="wide")
st.title("Geschäftsbericht auswerten")

# Diese Seite braucht den KI-Schlüssel (.env) und das EU-Register (data/raw/). Beides liegt
# bewusst NICHT im Repository – online (Streamlit Cloud) wird die Seite deshalb abgeschaltet.
LOKAL = os.path.exists("data/raw/ets_2025.xlsx") and (
    os.path.exists(".env") or bool(os.environ.get("GEMINI_API_KEY")))
if not LOKAL:
    st.info("Die Upload-Seite läuft nur lokal auf dem Rechner des Autors: Sie nutzt einen "
            "persönlichen KI-Schlüssel und das EU-Emissionsregister als lokale Datei.")
    st.stop()

from src import bericht_auswertung as ba   # noqa: E402 – erst nach der Prüfung laden
from src.ets_suche import anlagen_suchen, register_laden, zusammenfassen   # noqa: E402
from src.modell import KONZERN_ORDNER   # noqa: E402

st.warning("**Nur öffentliche Geschäftsberichte hochladen.** "
           "Der Text wird an die kostenlose Gemini-API gesendet.")

# ---------- 1. Bericht und Stammdaten ----------
st.header("1. Bericht hochladen")
datei = st.file_uploader("Geschäftsbericht als PDF hierher ziehen", type="pdf")

spalte1, spalte2, spalte3 = st.columns(3)
name = spalte1.text_input("Konzernname", placeholder="z. B. Salzgitter")
geschaeftsjahr = spalte2.text_input("Geschäftsjahr", placeholder="z. B. 2025 oder 2024/2025")
pruefer = spalte3.text_input("Abschlussprüfer", placeholder="z. B. KPMG")
if any(w in pruefer.lower() for w in ["pwc", "pricewaterhouse"]):
    st.error("PwC ist Abschlussprüfer: Diesen Konzern nicht veröffentlichen. "
             "Trag die gespeicherte Datei vor einem Commit in die .gitignore ein.")

spalte1, spalte2, spalte3 = st.columns(3)
boersenwert = spalte1.number_input("Börsenwert (Mio. €)", min_value=0.0, step=100.0)
kurs_datum = spalte2.date_input("Datum des Kurses", value=datetime.date.today())
kurs_quelle = spalte3.text_input("Quelle des Kurses", placeholder="z. B. onvista, Xetra-Schluss")

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
st.header("2. Kennzahlen per KI lesen")
schon_da = os.path.exists(ba.ergebnis_pfad(kenn))
if schon_da and st.session_state.get("kenn") != kenn:
    st.session_state["kennzahlen"] = ba.auswerten(pdf_pfad, kenn, name, geschaeftsjahr)  # nur laden
    st.session_state["kenn"] = kenn

if schon_da:
    st.success("Für diesen Bericht liegt schon eine Auswertung vor – es wird keine neue KI-Anfrage gestellt.")
else:
    st.write(f"{len(ba.KENNZAHLEN)} Anfragen an Gemini, je {ba.PAUSE} Sekunden Pause (ca. 1 Minute).")
    if st.button("KI-Auswertung starten", type="primary", disabled=not (name and geschaeftsjahr)):
        balken = st.progress(0.0, text="Lese PDF ein …")
        st.session_state["kennzahlen"] = ba.auswerten(
            pdf_pfad, kenn, name, geschaeftsjahr,
            fortschritt=lambda anteil, frage: balken.progress(anteil, text=f"Fertig: {frage[:60]} …"))
        st.session_state["kenn"] = kenn
        st.rerun()
    if not (name and geschaeftsjahr):
        st.caption("Bitte zuerst Konzernname und Geschäftsjahr eintragen.")

if st.session_state.get("kenn") != kenn:
    st.stop()

# ---------- 3. Vier-Augen-Prüfung ----------
st.header("3. Werte von Hand prüfen")
st.write("Öffne den Bericht auf der angegebenen Seite und vergleiche. Nur die Spalte "
         "**Geprüfter Wert** ist bearbeitbar.")
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
st.header("4. EU-ETS-Anlagen zuordnen")


@st.cache_data
def register():
    return register_laden()


begriffe = st.text_input("Suchbegriffe, durch Komma getrennt (Konzern, Tochtergesellschaften, Standorte)",
                         value=name)
kandidaten = anlagen_suchen(register(), begriffe.split(",")) if begriffe.strip() else None
ets = None
if kandidaten is not None:
    st.caption(f"{len(kandidaten)} Treffer. Hake nur Anlagen an, die wirklich zum Konzern gehören; "
               "bei Gemeinschaftsunternehmen den Anteil anpassen (z. B. 0,5).")
    auswahl = st.data_editor(kandidaten, hide_index=True, key=f"ets_{kenn}_{begriffe}",
                             disabled=[s for s in kandidaten.columns
                                       if s not in ("Aufnehmen", "Anteil", "Standort")])
    ets = zusammenfassen(auswahl, zahl("scope1") or None)
    a, b, c, d = st.columns(4)
    a.metric("Emissionen 2025", f"{ets['emissionen_2025']:.2f} Mio. t")
    b.metric("Gratiszuteilung 2025", f"{ets['zuteilung_2025']:.2f} Mio. t")
    c.metric("Deckungsgrad", f"{ets['deckungsgrad']:.0%}" if ets["deckungsgrad"] else "–")
    if ets["anzahl"] and ets["abweichung_2025"] is not None:
        d.metric("Abstimmung mit Scope 1", f"{ets['abweichung_2025']:+.1f} % (2025)",
                 f"{ets['abweichung_2024']:+.1f} % (2024)", delta_color="off")
    st.caption("Die ETS-Werte gelten je Kalenderjahr. Weicht das Geschäftsjahr ab, ist auch die "
               "Abstimmung mit 2024 aussagekräftig. Große Abweichungen = Anlagen fehlen oder sind zu viel.")

# ---------- 5. Modellparameter ----------
st.header("5. Modellparameter")
jahr = ba.berichtsjahr(geschaeftsjahr)
scope1 = zahl("scope1")
ets_e = ets["emissionen_2025"] if ets and ets["anzahl"] else 0.0
bepreist_vorschlag = min(ets_e / scope1, 1.0) if scope1 and ets_e else 1.0
st.caption("Vorschläge aus KI und ETS – alles bearbeitbar. Bepreiste Emissionen = Scope 1 × bepreister Anteil.")

spalte1, spalte2, spalte3 = st.columns(3)
anteil_bepreist = spalte1.number_input("Bepreister Anteil (ETS / Scope 1)", 0.0, 1.0,
                                       begrenzt(round(bepreist_vorschlag, 3), 0.0, 1.0), step=0.01)
emissionen = spalte2.number_input("Bepreiste Emissionen 2025 (Mio. t)", 0.0, None,
                                  max(round(scope1 * anteil_bepreist, 3), 0.0), step=0.1)
deckungsgrad = spalte3.number_input("Deckungsgrad Gratiszuteilung", 0.0, 3.0,
                                    begrenzt(round(ets["deckungsgrad"], 3), 0.0, 3.0)
                                    if ets and ets["deckungsgrad"] else 1.0, step=0.01)
reduktion = spalte1.number_input(
    "Reduktion pro Jahr bis 2030", 0.0, 0.5,
    begrenzt(round(ba.reduktion_pro_jahr(zahl("ziel_aktuell"), zahl("ziel_wert"),
                                         zahl("ziel_jahr"), jahr), 4), 0.0, 0.5),
    step=0.005, format="%.4f",
    help="Aus Klimaziel: 1 − (Ziel / aktuell)^(1 / Jahre). Bei Intensitätszielen nur eine Näherung.")
steuersatz = spalte2.number_input("Steuersatz", 0.0, 0.6,
                                  begrenzt(round(zahl("steuersatz", 30) / 100, 4), 0.0, 0.6), step=0.005)
wacc = spalte3.number_input("WACC nach Steuern", 0.01, 0.2,
                            begrenzt(round(zahl("wacc", 8) / 100, 4), 0.01, 0.2), step=0.001)
spalte1.metric("Unternehmenswert (Mio. €)",
               f"{boersenwert + zahl('nettofinanzschulden') + zahl('pensionen'):,.0f}")

# ---------- 6. Speichern ----------
st.header("6. Konzern speichern")
alle_geprueft = st.checkbox("Alle Werte geprüft (Vier-Augen-Prinzip: im Bericht nachgeschlagen)")
fehlt = [t for t, ok in [("Konzernname", name), ("Geschäftsjahr", geschaeftsjahr),
                         ("Börsenwert", boersenwert > 0), ("Kursquelle", kurs_quelle)] if not ok]
if fehlt:
    st.caption("Noch offen: " + ", ".join(fehlt))

if st.button("Konzern speichern", type="primary", disabled=not alle_geprueft or bool(fehlt)):
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
    st.success(f"Gespeichert: konzerne/{kurz}.json – auf der Hauptseite links unter „Konzern“ auswählbar.")

"""
CO2-Stresstest – Web-App.  Start im Terminal:  streamlit run app.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from src.modell import (CBAM_PFADE, alle_konzerne, barwert_gesamt, jahresrechnung,
                        monte_carlo, szenario_anwenden, tornado, unternehmenswert)

st.set_page_config(page_title="CO₂-Stresstest", page_icon="🏭", layout="wide")
KONZERNE = alle_konzerne()   # fest eingetragene + über die Upload-Seite gespeicherte
st.title("CO₂-Stresstest für Industriekonzerne")
st.caption("Wie stark belasten steigende CO₂-Kosten den Unternehmenswert? "
           "Daten: EU-Emissionshandelsregister, Geschäftsberichte 2025, eigene Annahmen.")

# --- Seitenleiste: die Regler ------------------------------------------
with st.sidebar:
    st.header("Annahmen")
    name = st.selectbox("Konzern", list(KONZERNE))
    preis_2030 = st.slider("CO₂-Preis 2030 (€/t)", 50, 200, 100, step=5)
    anstieg = st.slider("Preisanstieg nach 2030 (€/t pro Jahr)", 0.0, 10.0, 5.4, step=0.2)
    weitergabe = st.slider("Weitergabe an Kunden (%)", 0, 100, 40, step=5) / 100
    ziel = st.slider("Erreichung Klimaziel 2050 (%)", 0, 100, 65, step=5) / 100
    cbam_name = st.radio("CBAM-Pfad", list(CBAM_PFADE))

    with st.expander("Unternehmensszenarien"):
        st.caption("Alle Regler auf Standard = Basisfall. Bei Heidelberg und Thyssenkrupp "
                   "sind die Emissionen schon auf bepreiste Mengen begrenzt (100 %).")
        szenario = {
            "verzoegerung_jahre": st.slider("Verzögerung der Emissionssenkung (Jahre)", 0, 10, 0),
            "anteil_bepreist": st.slider("Anteil Emissionen mit CO₂-Preis (%)",
                                         0, 100, 100, step=5) / 100,
            "abspaltung_emissionen": st.slider("Abspaltung: Anteil Emissionen (%)",
                                               0, 100, 0, step=5) / 100,
            "abspaltung_wert": st.slider("Abspaltung: Anteil Unternehmenswert (%)",
                                         0, 90, 0, step=5) / 100,
        }

# --- Rechnen -----------------------------------------------------------
k = szenario_anwenden(KONZERNE[name], szenario)
tabelle = jahresrechnung(k, preis_2030, anstieg, weitergabe, ziel, CBAM_PFADE[cbam_name])
barwert = barwert_gesamt(k, tabelle)
anteil = barwert / unternehmenswert(k) * 100

# --- Kennzahlen oben ---------------------------------------------------
spalte1, spalte2, spalte3 = st.columns(3)
spalte1.metric("Barwert der CO₂-Kosten", f"{barwert / 1000:.1f} Mrd. €")
spalte2.metric("in % des Unternehmenswerts", f"{anteil:.1f} %")
spalte3.metric("CO₂-Kosten 2030 (vor Steuern)", f"{tabelle.loc[2030, 'Kosten']:,.0f} Mio. €")

reiter1, reiter2, reiter3 = st.tabs(["Kostenverlauf", "Unsicherheit", "KI-Prüfspur"])

with reiter1:
    diagramm = tabelle.set_index(tabelle.index.astype(str))   # Jahre als Text, sonst "2,026"
    st.subheader("Emissionen und Gratiszuteilung (Mio. t CO₂)")
    st.line_chart(diagramm[["Emissionen", "Gratiszuteilung"]])
    st.subheader("CO₂-Kosten vor Steuern (Mio. €)")
    st.bar_chart(diagramm["Kosten"])
    with st.expander("Jahrestabelle anzeigen"):
        st.dataframe(tabelle.round(1))


@st.cache_data
def simulation(konzern_name, szenario):
    """Wird je Konzern und Szenario nur einmal gerechnet und dann zwischengespeichert."""
    return monte_carlo(szenario_anwenden(KONZERNE[konzern_name], szenario))


@st.cache_data
def tornado_rechnen(konzern_name, szenario):
    return tornado(szenario_anwenden(KONZERNE[konzern_name], szenario))


with reiter2:
    st.write("10.000 Szenarien mit zufällig gezogenen Annahmen "
             "(unabhängig von den Reglern oben links, aber mit dem gewählten Unternehmensszenario).")
    mc = simulation(name, szenario)
    a, b, c = st.columns(3)
    a.metric("Median", f"{np.median(mc):.1f} %")
    b.metric("90-%-Bandbreite", f"{np.percentile(mc, 5):.1f} – {np.percentile(mc, 95):.1f} %")
    c.metric("Wahrscheinlichkeit > 20 %", f"{(mc > 20).mean():.0%}")
    anzahl, grenzen = np.histogram(mc, bins=40)
    mitte = ((grenzen[:-1] + grenzen[1:]) / 2).round(1)
    st.bar_chart(pd.Series(anzahl, index=mitte, name="Anzahl Szenarien"))

    st.subheader("Welche Annahme treibt das Ergebnis?")
    st.caption("Alle Annahmen auf ihrem Median, dann jeweils eine auf ihr 5-%- bzw. 95-%-Quantil.")
    sensitiv, basiswert = tornado_rechnen(name, szenario)
    grafik, achse = plt.subplots(figsize=(8, 3.5))
    achse.barh(sensitiv["Annahme"], sensitiv["Spanne"], left=sensitiv["Tief"], color="#2a6f97")
    achse.axvline(basiswert, color="black", linestyle="--", label=f"Basis {basiswert:.1f} %")
    achse.set_xlabel("Barwert der CO₂-Kosten in % des Unternehmenswerts")
    achse.legend()
    links, _ = st.columns([3, 2])   # Diagramm nur auf 60 % der Breite
    links.pyplot(grafik)

with reiter3:
    st.write("Kennzahlen, die die KI (Gemini) aus dem Geschäftsbericht gelesen hat – "
             "mit Seitenzahl und wörtlichem Zitat, automatisch gegen eine "
             "manuell geprüfte Referenz abgeglichen.")
    if os.path.exists(k["pruefspur"]):
        st.dataframe(pd.read_csv(k["pruefspur"]), hide_index=True)
    else:
        st.info("Für diesen Konzern liegt noch keine KI-Prüfspur vor.")
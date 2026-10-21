"""
CarbonCliff – carbon cost stress test (Streamlit web app).
Run locally:  streamlit run app.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from src.modell import (CBAM_PFADE, alle_konzerne, barwert_gesamt, jahresrechnung,
                        monte_carlo, szenario_anwenden, tornado, unternehmenswert)

# Display names (the model keeps its internal German keys)
CBAM_ANZEIGE = {"Geltendes Recht": "Current law", "Kommissionsvorschlag 2026": "Commission proposal 2026"}
SPALTEN = {"Emissionen": "Emissions", "Gratiszuteilung": "Free allocation", "Zukauf": "Purchased",
           "Preis": "Price (€/t)", "Kosten": "Cost before tax", "Nach Steuern": "Cost after tax",
           "Barwert": "Present value"}

st.set_page_config(page_title="CarbonCliff", page_icon="🏭", layout="wide")
KONZERNE = alle_konzerne()   # built-in companies + companies saved via the upload page
st.title("CarbonCliff – carbon cost stress test for heavy industry")
st.caption("How much enterprise value is at risk when free EU carbon allowances are phased out? "
           "Data: EU emissions trading registry, annual reports, own assumptions. "
           "Private student project · public data only · not investment advice.")

# --- Sidebar: assumptions ---------------------------------------------
with st.sidebar:
    st.header("Assumptions")
    name = st.selectbox("Company", list(KONZERNE))
    preis_2030 = st.slider("Carbon price 2030 (€/t)", 50, 200, 100, step=5)
    anstieg = st.slider("Price increase after 2030 (€/t per year)", 0.0, 10.0, 5.4, step=0.2)
    weitergabe = st.slider("Pass-through to customers (%)", 0, 100, 40, step=5) / 100
    ziel = st.slider("Climate target achieved by 2050 (%)", 0, 100, 65, step=5) / 100
    cbam_name = st.radio("CBAM phase-out path", list(CBAM_PFADE), format_func=CBAM_ANZEIGE.get)

    with st.expander("Company scenarios"):
        st.caption("All sliders at default = base case. For the built-in companies, emissions "
                   "are already limited to priced volumes (100 %).")
        szenario = {
            "verzoegerung_jahre": st.slider("Delay of emission reductions (years)", 0, 10, 0),
            "anteil_bepreist": st.slider("Share of emissions with a carbon price (%)",
                                         0, 100, 100, step=5) / 100,
            "abspaltung_emissionen": st.slider("Spin-off: share of emissions (%)",
                                               0, 100, 0, step=5) / 100,
            "abspaltung_wert": st.slider("Spin-off: share of enterprise value (%)",
                                         0, 90, 0, step=5) / 100,
        }

# --- Calculation -------------------------------------------------------
k = szenario_anwenden(KONZERNE[name], szenario)
tabelle = jahresrechnung(k, preis_2030, anstieg, weitergabe, ziel, CBAM_PFADE[cbam_name])
barwert = barwert_gesamt(k, tabelle)
anteil = barwert / unternehmenswert(k) * 100

# --- Key figures -------------------------------------------------------
spalte1, spalte2, spalte3 = st.columns(3)
spalte1.metric("Present value of carbon costs", f"€{barwert / 1000:.1f}bn")
spalte2.metric("Share of enterprise value", f"{anteil:.1f} %")
spalte3.metric("Carbon cost 2030 (before tax)", f"€{tabelle.loc[2030, 'Kosten']:,.0f}m")

reiter1, reiter2, reiter3 = st.tabs(["Cost path", "Uncertainty", "AI audit trail"])

with reiter1:
    diagramm = tabelle.rename(columns=SPALTEN)
    diagramm = diagramm.set_index(diagramm.index.astype(str))   # years as text, otherwise "2,026"
    st.subheader("Emissions and free allocation (Mt CO₂)")
    st.line_chart(diagramm[["Emissions", "Free allocation"]])
    st.subheader("Carbon cost before tax (€m)")
    st.bar_chart(diagramm["Cost before tax"])
    with st.expander("Show annual table"):
        st.dataframe(tabelle.rename(columns=SPALTEN).round(1))


@st.cache_data
def simulation(konzern_name, szenario):
    """Computed once per company and scenario, then cached."""
    return monte_carlo(szenario_anwenden(KONZERNE[konzern_name], szenario))


@st.cache_data
def tornado_rechnen(konzern_name, szenario):
    return tornado(szenario_anwenden(KONZERNE[konzern_name], szenario))


with reiter2:
    st.write("10,000 scenarios with randomly drawn assumptions "
             "(independent of the sliders above, but using the selected company scenario).")
    mc = simulation(name, szenario)
    a, b, c = st.columns(3)
    a.metric("Median", f"{np.median(mc):.1f} %")
    b.metric("90 % range", f"{np.percentile(mc, 5):.1f} – {np.percentile(mc, 95):.1f} %")
    c.metric("Probability > 20 %", f"{(mc > 20).mean():.0%}")
    anzahl, grenzen = np.histogram(mc, bins=40)
    mitte = ((grenzen[:-1] + grenzen[1:]) / 2).round(1)
    st.bar_chart(pd.Series(anzahl, index=mitte, name="Number of scenarios"))

    st.subheader("Which assumption drives the result?")
    st.caption("All assumptions at their median, then one at a time moved to its 5 % or 95 % quantile.")
    sensitiv, basiswert = tornado_rechnen(name, szenario)
    grafik, achse = plt.subplots(figsize=(8, 3.5))
    achse.barh(sensitiv["Annahme"], sensitiv["Spanne"], left=sensitiv["Tief"], color="#2a6f97")
    achse.axvline(basiswert, color="black", linestyle="--", label=f"Base {basiswert:.1f} %")
    achse.set_xlabel("Present value of carbon costs in % of enterprise value")
    achse.legend()
    links, _ = st.columns([3, 2])   # chart on 60 % of the width
    links.pyplot(grafik)

with reiter3:
    st.write("Figures read by the AI (Gemini) from the annual report – with page number and "
             "verbatim quote, automatically checked against a manually verified reference.")
    if os.path.exists(k["pruefspur"]):
        spur = pd.read_csv(k["pruefspur"]).rename(columns={
            "Kennzahl": "Figure", "Referenz": "Reference", "KI-Wert": "AI value", "Seite": "Page",
            "Wert korrekt": "Value correct", "Zitat belegt": "Quote verified", "Zitat": "Quote",
            "Geprüfter Wert": "Verified value", "Korrigiert": "Corrected"})
        st.dataframe(spur, hide_index=True)
    else:
        st.info("No AI audit trail available for this company yet.")

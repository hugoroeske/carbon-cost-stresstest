"""
Ranking: welche Konzerne trifft der Wegfall der Gratiszuteilung am stärksten?
Alle Konzerne werden mit denselben Annahmen gerechnet (src/modell.py: ranking).
"""
import os

import pandas as pd
import streamlit as st

from src.modell import CBAM_PFADE, EINHEITLICH, ranking, ranking_laden

CBAM_ANZEIGE = {"Geltendes Recht": "Current law", "Kommissionsvorschlag 2026": "Commission proposal 2026"}
BRANCHE = {"Stahl": "Steel", "Zement": "Cement", "Aluminium": "Aluminium"}

st.set_page_config(page_title="CarbonCliff ranking", page_icon="📊", layout="wide")
st.title("Which companies does the end of free allocation hit hardest?")
st.caption("All companies use the same assumptions, so only their carbon exposure differs. "
           "Emissions are held at the 2025 level until 2030 (company decarbonisation plans are not included). "
           "Model results under stated assumptions – not investment advice.")

daten = ranking_laden()

with st.expander("Common assumptions", expanded=False):
    s1, s2, s3 = st.columns(3)
    preis = s1.slider("Carbon price 2030 (€/t)", 50, 200, EINHEITLICH["preis_2030"], step=5)
    weitergabe = s2.slider("Pass-through to customers (%)", 0, 100, int(EINHEITLICH["weitergabe"] * 100), step=5) / 100
    wacc = s3.slider("Discount rate (WACC, %)", 5.0, 12.0, EINHEITLICH["wacc"] * 100, step=0.5) / 100
    cbam = s1.radio("CBAM phase-out path", list(CBAM_PFADE), format_func=CBAM_ANZEIGE.get)
    st.caption(f"Fixed for all: tax rate {EINHEITLICH['steuersatz']:.0%}, price increase "
               f"{EINHEITLICH['anstieg']} €/t per year after 2030, climate target achieved by 2050: "
               f"{EINHEITLICH['zielerreichung']:.0%}.")

ergebnis = ranking(daten, preis_2030=preis, weitergabe=weitergabe, wacc=wacc, cbam=cbam)
mit_wert = ergebnis.dropna(subset=["Anteil am Unternehmenswert"])

# --- Chart ----------------------------------------------------------------
st.subheader("Present value of additional carbon costs in % of enterprise value")
grafik = mit_wert.set_index("Konzern")["Anteil am Unternehmenswert"] * 100
st.bar_chart(grafik.rename("% of enterprise value"), horizontal=True, sort=False)

# --- Table ----------------------------------------------------------------
tabelle = pd.DataFrame({
    "Rank": ergebnis["Rang"],
    "Company": ergebnis["Konzern"],
    "Sector": ergebnis["Branche"].map(BRANCHE),
    "EU ETS emissions 2025 (Mt)": ergebnis["Emissionen 2025 (Mt)"].round(2),
    "Free allocation coverage": (ergebnis["Deckungsgrad"] * 100).round(0).astype(int).astype(str) + " %",
    "First year of purchases": ergebnis["Erster Zukauf"].astype("Int64").astype(str),
    "PV of carbon costs (€bn)": ergebnis["Barwert CO2 (Mrd. €)"].round(1),
    "Enterprise value (€bn)": ergebnis["Unternehmenswert (Mrd. €)"].round(1),
    "% of enterprise value": (ergebnis["Anteil am Unternehmenswert"] * 100).round(1),
    "Emissions with uncertain assignment": (ergebnis["Anteil unsicher zugeordnet"] * 100).round(0).astype(int).astype(str) + " %",
})
st.dataframe(tabelle, hide_index=True, width="stretch")

# --- Robustness -----------------------------------------------------------
st.subheader("Does the ranking change under other assumptions?")
varianten = {"Base": {}, "Pass-through 20 %": {"weitergabe": 0.2}, "Pass-through 60 %": {"weitergabe": 0.6},
             "Commission proposal": {"cbam": "Kommissionsvorschlag 2026"}, "WACC 10 %": {"wacc": 0.10},
             "Carbon price 150 €/t": {"preis_2030": 150}}
raenge = pd.DataFrame({name: ranking(daten, **v).dropna(subset=["Anteil am Unternehmenswert"])
                       .set_index("Konzern")["Rang"] for name, v in varianten.items()})
raenge.index.name = "Company"
st.dataframe(raenge.sort_values("Base"), width="stretch")
st.caption("Common assumptions move all companies in the same direction, so the order mainly reflects "
           "emissions relative to enterprise value and how well free allocation covers today's emissions. "
           "Company-specific uncertainty (plant matching, decarbonisation plans) is not captured here.")

# --- Notes ----------------------------------------------------------------
with st.expander("Method, sources and limitations"):
    st.markdown("""
- **Emissions and free allocation:** EU Union Registry, verified emissions 2025, matched to companies by name
  and site; joint ventures pro rata (e.g. HKM: Thyssenkrupp 50 %, Salzgitter 30 %). Accounts without 2025 data
  use the 2024 value; allocation without production ("ghost plants") is excluded.
- **Enterprise value:** market capitalisation (October 2026) + net financial debt + pension provisions from the
  latest annual results, converted at ECB rates of 31 Dec 2025. Sources per company: `src/ranking_daten.json`.
- **Coverage above 100 %** (e.g. ArcelorMittal) partly reflects allowances for waste gases delivered to third-party
  power plants – exposure is probably understated.
- **Not included:** decarbonisation plans (e.g. electric arc furnaces at SSAB and voestalpine), carbon prices
  outside the EU, indirect emissions from electricity.
- Companies are only shown if their auditor could be verified and is not the author's employer.
""")
    pfad = "ergebnisse/ranking_anlagen.csv"
    if os.path.exists(pfad):
        st.download_button("Download installation list (CSV)", open(pfad, "rb").read(),
                           file_name="carboncliff_installations.csv")

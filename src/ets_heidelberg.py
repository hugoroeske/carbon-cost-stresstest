"""
Heidelberg-Anlagen aus den EU-ETS-Daten herausfiltern und für 2025
Emissionen, Gratiszuteilung und Zukaufbedarf berechnen.
"""
import os
import pandas as pd

pd.set_option("display.width", 200)       # breitere Ausgabe im Terminal
pd.set_option("display.max_columns", 20)  # keine Spalten mit "..." verstecken

DATEI = "data/raw/ets_2025.xlsx"
CO2_PREIS_2025 = 73          # €/t, Durchschnitt 2025 (Geschäftsbericht S. 48)
REFERENZ_BERICHT = 22.2e6    # t CO2e in Ländern mit CO2-Preis (S. 121)

## --- 1. Richtiges Tabellenblatt und Kopfzeile finden ------------------
# Die EU-Datei kann mehrere Tabellenblätter haben (z. B. ein Infoblatt).
# Wir lesen ALLE Blätter ein und suchen das, in dem "REGISTRY_CODE" steht.
print("Lese Excel-Datei ein (kann bis zu einer Minute dauern) ...")
alle_blaetter = pd.read_excel(DATEI, header=None, sheet_name=None)
print(f"Tabellenblätter in der Datei: {list(alle_blaetter)}")

df = None
for name, roh in alle_blaetter.items():
    # Text vereinheitlichen: unsichtbare Leerzeichen am Rand entfernen
    zellen = roh.astype(str).apply(lambda spalte: spalte.str.strip())
    gefunden = (zellen == "REGISTRY_CODE").any(axis=1)
    if gefunden.any():
        kopfzeile = gefunden.idxmax()          # erste Zeile mit Treffer
        df = roh.iloc[kopfzeile + 1:].copy()   # alles unterhalb = Daten
        df.columns = zellen.iloc[kopfzeile]    # Treffer-Zeile = Spaltennamen
        print(f"Daten gefunden in Blatt '{name}', Kopfzeile in Zeile {kopfzeile + 1}")
        break

if df is None:
    raise SystemExit("REGISTRY_CODE nicht gefunden – bitte Datei prüfen.")
print(f"Fertig: {len(df)} Zeilen eingelesen.")
# --- 2. Nur die Spalten behalten, die wir brauchen --------------------
zuteilung_spalten = ["ALLOCATION_2025", "ALLOCATION_RESERVE_2025",
                     "ALLOCATION_TRANSITIONAL_2025"]
df = df[["REGISTRY_CODE", "IDENTIFIER_IN_REG", "INSTALLATION_NAME",
         "MAIN_ACTIVITY_TYPE_CODE", "VERIFIED_EMISSIONS_2025"]
        + zuteilung_spalten]

# --- 3. "n/a" in echte Zahlen umwandeln -------------------------------
# Text wie "n/a" kann man nicht addieren. errors="coerce" macht daraus
# einen leeren Wert, den pandas beim Summieren überspringt.
for spalte in ["VERIFIED_EMISSIONS_2025"] + zuteilung_spalten:
    df[spalte] = pd.to_numeric(df[spalte], errors="coerce")

# --- 4. Heidelberg-Anlagen finden -------------------------------------
# Wir suchen "heidelberg" im Betreibernamen, Groß-/Kleinschreibung egal.
treffer = df["IDENTIFIER_IN_REG"].str.contains("heidelberg", case=False, na=False)
hm = df[treffer].copy()

# --- 5. Zuteilung und Zukaufbedarf pro Anlage -------------------------
hm["ZUTEILUNG"] = hm[zuteilung_spalten].sum(axis=1)
hm["ZUKAUF"] = hm["VERIFIED_EMISSIONS_2025"] - hm["ZUTEILUNG"]

# --- 5b. Prüfung: Anlagen mit Zuteilung, aber ohne Emissionen 2025 -----
ohne_emissionen = hm[hm["VERIFIED_EMISSIONS_2025"].isna()]
print(f"\nAnlagen ohne Emissionsangabe 2025: {len(ohne_emissionen)}")
print(ohne_emissionen[["REGISTRY_CODE", "IDENTIFIER_IN_REG",
                       "INSTALLATION_NAME", "ZUTEILUNG"]])

# --- 6. Ergebnis ausgeben ---------------------------------------------
nach_land = (hm.groupby("REGISTRY_CODE")
               [["VERIFIED_EMISSIONS_2025", "ZUTEILUNG", "ZUKAUF"]]
               .sum() / 1e6)          # in Mio. t
nach_land["ANLAGEN"] = hm.groupby("REGISTRY_CODE").size()

print(f"\nGefundene Heidelberg-Anlagen: {len(hm)}\n")
print("Nach Land (Mio. t CO2):")
print(nach_land.sort_values("VERIFIED_EMISSIONS_2025", ascending=False).round(2))

emissionen = hm["VERIFIED_EMISSIONS_2025"].sum()
zukauf = hm["ZUKAUF"].sum()
print(f"\nEmissionen gesamt:  {emissionen / 1e6:.2f} Mio. t")
print(f"Gratiszuteilung:    {hm['ZUTEILUNG'].sum() / 1e6:.2f} Mio. t")
print(f"Zukaufbedarf:       {zukauf / 1e6:.2f} Mio. t")
print(f"Kosten bei {CO2_PREIS_2025} €/t: {zukauf * CO2_PREIS_2025 / 1e6:.0f} Mio. €")
print(f"\nAbdeckung ggü. Geschäftsbericht: {emissionen / REFERENZ_BERICHT:.0%}")

# --- 7. Ergebnis für spätere Schritte speichern -----------------------
os.makedirs("data/processed", exist_ok=True)
hm.to_csv("data/processed/heidelberg_ets_2025.csv", index=False)

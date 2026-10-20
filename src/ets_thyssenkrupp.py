"""
Thyssenkrupp im EU-Emissionshandel:
Anlagen zuordnen, je Standort zusammenfassen und mit dem Geschäftsbericht abstimmen.
"""
import os
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

DATEI = "data/raw/ets_2025.xlsx"
BERICHT_SCOPE1 = 19.8   # Mio. t CO2e, Geschäftsbericht 2024/25 S. 123 (enthält ETS-Kalenderjahr 2024)

# ---------- Block 1: Zuordnungstabelle ----------
# Anlagenname im Register: (Standort, Anteil Thyssenkrupp, Begründung)
ANLAGEN = {
    "Integriertes Hüttenwerk Duisburg":                   ("Duisburg Nord", 1.0, "Name eindeutig"),
    "Heizkraftwerk ThyssenKrupp Stahl AG Duisburg Hamb.": ("Duisburg Nord", 1.0, "Name eindeutig"),
    "Kokerei Duisburg Schwelgern":                         ("Duisburg Nord", 1.0, "anonymes Konto 83, über Abstimmung"),
    "Kraftwerk Hamborn Block 5":                           ("Duisburg Nord", 1.0, "Hüttengas-Kraftwerk, über Abstimmung"),
    "Dampfkesselanlage Duisburg Hamborn":                  ("Duisburg Nord", 1.0, "Hüttengas-Kraftwerk, über Abstimmung"),
    "Glocke Duisburg":                                     ("HKM Huckingen", 0.5, "anonymes Konto 71, über Abstimmung"),
    "Kraftwerk Huckingen":                                 ("HKM Huckingen", 0.5, "Kontoname enthält HKM"),
    "Kohlenmahl- und Trocknungsanlage":                    ("HKM Huckingen", 0.5, "Kontoname enthält HKM"),
    "Warmwalzwerk Hohenlimburg":                           ("Hohenlimburg",  1.0, "Kontoname thyssenkrupp Hohenlimburg"),
    "Kaltwalzwerk 2 mit Nebenanlagen":                     ("Andernach",     1.0, "Kontoname thyssenkrupp Rasselstein"),
}

# ---------- Block 2: Register einlesen (wie bei Heidelberg) ----------
blaetter = pd.read_excel(DATEI, sheet_name=None, header=None)
for name, roh in blaetter.items():
    roh = roh.map(lambda x: x.strip() if isinstance(x, str) else x)
    treffer = (roh == "REGISTRY_CODE").any(axis=1)
    if treffer.any():
        kopf = treffer.idxmax()
        df = roh.iloc[kopf + 1:].copy()
        df.columns = roh.iloc[kopf]
        df.columns.name = None          # sonst steht oben links eine störende "2"
        print(f"Blatt '{name}': {len(df)} Anlagen eingelesen")
        break

# Doppelte Leerzeichen im Namen vereinheitlichen ("Kraftwerk  Hamborn" -> "Kraftwerk Hamborn")
df["NAME"] = df["INSTALLATION_NAME"].astype(str).str.replace(r"\s+", " ", regex=True)

# ---------- Block 3: Zahlen umwandeln, Gratiszuteilung bilden ----------
spalten = ["ALLOCATION_2025", "ALLOCATION_RESERVE_2025", "ALLOCATION_TRANSITIONAL_2025",
           "VERIFIED_EMISSIONS_2025", "VERIFIED_EMISSIONS_2024"]
for s in spalten:
    df[s] = pd.to_numeric(df[s], errors="coerce").fillna(0)
df["ZUTEILUNG"] = df[["ALLOCATION_2025", "ALLOCATION_RESERVE_2025",
                      "ALLOCATION_TRANSITIONAL_2025"]].sum(axis=1)

# ---------- Block 4: Anlagen auswählen und Vollständigkeit prüfen ----------
tk = df[(df["REGISTRY_CODE"] == "DE") & (df["NAME"].isin(ANLAGEN))].copy()
gefunden = tk["NAME"].value_counts()
for anlage in ANLAGEN:
    anzahl = gefunden.get(anlage, 0)
    if anzahl != 1:
        raise ValueError(f"'{anlage}' wurde {anzahl}-mal gefunden statt genau einmal")
print(f"Alle {len(ANLAGEN)} Anlagen genau einmal gefunden")

tk["STANDORT"] = tk["NAME"].map(lambda n: ANLAGEN[n][0])
tk["ANTEIL"]   = tk["NAME"].map(lambda n: ANLAGEN[n][1])

# ---------- Block 5: Anteil anwenden (HKM nur zu 50 %) ----------
tk["EMISSIONEN_2025"] = tk["VERIFIED_EMISSIONS_2025"] * tk["ANTEIL"]
tk["EMISSIONEN_2024"] = tk["VERIFIED_EMISSIONS_2024"] * tk["ANTEIL"]
tk["ZUTEILUNG_ANTEIL"] = tk["ZUTEILUNG"] * tk["ANTEIL"]

print("\nEinzelne Anlagen (Mio. t):")
einzeln = tk[["STANDORT", "NAME", "ANTEIL", "ZUTEILUNG_ANTEIL", "EMISSIONEN_2025"]].copy()
einzeln[["ZUTEILUNG_ANTEIL", "EMISSIONEN_2025"]] /= 1e6
print(einzeln.sort_values(["STANDORT", "EMISSIONEN_2025"], ascending=[True, False]).round(2).to_string(index=False))

# ---------- Block 6: Je Standort zusammenfassen ----------
standorte = tk.groupby("STANDORT")[["ZUTEILUNG_ANTEIL", "EMISSIONEN_2025"]].sum() / 1e6
standorte["DECKUNG_%"] = standorte["ZUTEILUNG_ANTEIL"] / standorte["EMISSIONEN_2025"] * 100
print("\nJe Standort (Mio. t):")
print(standorte.round(2).to_string())

summe_e = standorte["EMISSIONEN_2025"].sum()
summe_z = standorte["ZUTEILUNG_ANTEIL"].sum()
print(f"\nKonzern 2025: Emissionen {summe_e:.2f} Mio. t | Gratiszuteilung {summe_z:.2f} Mio. t "
      f"| Deckungsgrad {summe_z / summe_e * 100:.0f} %")

# ---------- Block 7: Abstimmung mit dem Geschäftsbericht ----------
summe_2024 = tk["EMISSIONEN_2024"].sum() / 1e6
abweichung = (summe_2024 / BERICHT_SCOPE1 - 1) * 100
print(f"Abstimmung: ETS 2024 = {summe_2024:.2f} Mio. t | Bericht = {BERICHT_SCOPE1} Mio. t "
      f"| Abweichung {abweichung:+.1f} %")

# ---------- Block 8: Speichern ----------
os.makedirs("data/processed", exist_ok=True)
tk.to_csv("data/processed/ets_thyssenkrupp.csv", index=False)
print("Gespeichert: data/processed/ets_thyssenkrupp.csv")
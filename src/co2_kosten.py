"""
CO2-Kosten von Heidelberg Materials 2026-2035 (feste Annahmen).
Alle Annahmen mit Quelle stehen in annahmen.md.
"""
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

# --- Annahmen ----------------------------------------------------------
JAHRE = range(2026, 2036)    # 2026 bis einschließlich 2035
EMISSIONEN_2025 = 22.2       # Mio. t, Länder mit CO2-Preis (GB S. 121)
REDUKTION_PRO_JAHR = 0.048   # aus Ziel 512 -> 400 kg/t bis 2030 (GB S. 42)
DECKUNGSGRAD = 1.00          # Gratiszuteilung 2025 / Emissionen 2025 (ETS-Auswertung)
PREIS_2025 = 73              # €/t (GB S. 48)
PREIS_2030 = 100             # €/t, interne Erwartung Heidelberg (GB S. 121)
STEUERSATZ = 0.252           # effektive Steuerquote 2025 (GB S. 241)
WACC = 0.081                 # nach Steuern, CGU Deutschland (GB S. 248)
WEITERGABE = 0.0             # Anteil der CO2-Kosten, der an Kunden geht
RCO_2025 = 3381              # Mio. €, ~EBIT (GB S. 338)

# Anteil der Gratiszuteilung, der übrig bleibt (CBAM-Faktor)
CBAM_GESETZ = {2026: .975, 2027: .95, 2028: .90, 2029: .775, 2030: .515,
               2031: .39, 2032: .265, 2033: .14, 2034: 0, 2035: 0}
CBAM_VORSCHLAG = {2026: .975, 2027: .95, 2028: .915, 2029: .81, 2030: .59,
                  2031: .48, 2032: .375, 2033: .27, 2034: .15, 2035: .15}


def co2_preis(jahr):
    """Linear von 73 € (2025) auf 100 € (2030), danach gleicher Anstieg."""
    anstieg = (PREIS_2030 - PREIS_2025) / 5
    return PREIS_2025 + anstieg * (jahr - 2025)


def rechne(cbam_faktoren):
    """Rechnet die CO2-Kosten Jahr für Jahr für einen CBAM-Pfad."""
    zeilen = []
    for jahr in JAHRE:
        t = jahr - 2025                                   # Jahre seit 2025
        emissionen = EMISSIONEN_2025 * (1 - REDUKTION_PRO_JAHR) ** t
        zuteilung = EMISSIONEN_2025 * DECKUNGSGRAD * cbam_faktoren[jahr]
        zukauf = max(emissionen - zuteilung, 0)           # Überschuss = 0
        preis = co2_preis(jahr)
        kosten = zukauf * preis * (1 - WEITERGABE)        # Mio. €
        nach_steuern = kosten * (1 - STEUERSATZ)
        barwert = nach_steuern / (1 + WACC) ** t
        zeilen.append([jahr, emissionen, zuteilung, zukauf, preis,
                       kosten, kosten / RCO_2025 * 100, nach_steuern, barwert])
    return pd.DataFrame(zeilen, columns=[
        "Jahr", "Emiss. Mt", "Zuteil. Mt", "Zukauf Mt", "Preis €/t",
        "Kosten Mio€", "% vom RCO", "n. Steuern", "Barwert"]).set_index("Jahr")


# --- Beide Szenarien rechnen und ausgeben ------------------------------
for name, faktoren in [("Geltendes Recht", CBAM_GESETZ),
                       ("Kommissionsvorschlag 2026", CBAM_VORSCHLAG)]:
    ergebnis = rechne(faktoren)
    print(f"\n=== {name} ===")
    print(ergebnis.round(1))
    print(f"Barwert 2026-2035: {ergebnis['Barwert'].sum():,.0f} Mio. €")
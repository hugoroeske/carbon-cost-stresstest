"""
CO2-Kosten von Heidelberg Materials 2026-2050 im Verhältnis zum Unternehmenswert.
Alle Annahmen mit Quelle stehen in annahmen.md.
"""
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

# --- Annahmen ----------------------------------------------------------
JAHRE = range(2026, 2051)    # 2026 bis einschließlich 2050
EMISSIONEN_2025 = 22.2       # Mio. t, Länder mit CO2-Preis (GB S. 121)
REDUKTION_PRO_JAHR = 0.048   # bis 2030: Ziel 512 -> 400 kg/t (GB S. 42)
DECKUNGSGRAD = 1.00          # Gratiszuteilung 2025 / Emissionen 2025 (ETS-Auswertung)
PREIS_2025 = 73              # €/t (GB S. 48)
PREIS_2030 = 100             # €/t, interne Erwartung Heidelberg (GB S. 121)
STEUERSATZ = 0.252           # effektive Steuerquote 2025 (GB S. 241)
WACC = 0.081                 # nach Steuern, CGU Deutschland (GB S. 248)
WEITERGABE = 0.0             # Anteil der CO2-Kosten, der an Kunden geht
RCO_2025 = 3381              # Mio. €, ~EBIT (GB S. 338)
BOERSENWERT = 25300          # Mio. €, 143,80 € x 175,8 Mio. Aktien (19.10.2026)
NETTOFINANZSCHULDEN = 5715   # Mio. € (GB S. 338)
UNTERNEHMENSWERT = BOERSENWERT + NETTOFINANZSCHULDEN

# Anteil der Gratiszuteilung, der übrig bleibt (CBAM-Faktor).
# Jahre, die nicht in der Liste stehen, bekommen 0 (= keine Gratiszuteilung).
CBAM_GESETZ = {2026: .975, 2027: .95, 2028: .90, 2029: .775, 2030: .515,
               2031: .39, 2032: .265, 2033: .14}
CBAM_VORSCHLAG = {2026: .975, 2027: .95, 2028: .915, 2029: .81, 2030: .59,
                  2031: .48, 2032: .375, 2033: .27,
                  2034: .15, 2035: .15, 2036: .15, 2037: .15}


def co2_preis(jahr):
    """Linear von 73 € (2025) auf 100 € (2030), danach gleicher Anstieg."""
    anstieg = (PREIS_2030 - PREIS_2025) / 5
    return PREIS_2025 + anstieg * (jahr - 2025)


def emissionen(jahr, ziel_erreicht):
    """Bis 2030 laut Konzernziel. Danach: linear auf 0 bis 2050 (Ziel
    erreicht) oder Stillstand auf dem Niveau von 2030 (Ziel verfehlt)."""
    if jahr <= 2030:
        return EMISSIONEN_2025 * (1 - REDUKTION_PRO_JAHR) ** (jahr - 2025)
    emissionen_2030 = EMISSIONEN_2025 * (1 - REDUKTION_PRO_JAHR) ** 5
    if ziel_erreicht:
        return emissionen_2030 * (2050 - jahr) / 20
    return emissionen_2030


def rechne(cbam_faktoren, ziel_erreicht, weitergabe=WEITERGABE):
    """Jahresrechnung 2026-2050. Gibt Tabelle und Gesamtbarwert zurück."""
    zeilen = []
    for jahr in JAHRE:
        t = jahr - 2025
        e = emissionen(jahr, ziel_erreicht)
        zuteilung = EMISSIONEN_2025 * DECKUNGSGRAD * cbam_faktoren.get(jahr, 0)
        zukauf = max(e - zuteilung, 0)
        kosten = zukauf * co2_preis(jahr) * (1 - weitergabe)
        nach_steuern = kosten * (1 - STEUERSATZ)
        barwert = nach_steuern / (1 + WACC) ** t
        zeilen.append([jahr, e, zuteilung, zukauf, kosten, nach_steuern, barwert])
    tabelle = pd.DataFrame(zeilen, columns=[
        "Jahr", "Emiss. Mt", "Zuteil. Mt", "Zukauf Mt",
        "Kosten Mio€", "n. Steuern", "Barwert"]).set_index("Jahr")

    # Restwert: Wird das Ziel verfehlt, fallen die Kosten von 2050 auch
    # danach jedes Jahr an (ewige Rente ohne Wachstum), abgezinst auf heute.
    restwert = 0
    if not ziel_erreicht:
        restwert = tabelle.loc[2050, "n. Steuern"] / WACC / (1 + WACC) ** 25

    return tabelle, tabelle["Barwert"].sum() + restwert


# # --- Szenarien rechnen: CBAM-Pfad x Klimaziel x Weitergabe -------------
WEITERGABE_SZENARIEN = [0.0, 0.3, 0.6, 1.0]

ergebnisse = []
for cbam_name, cbam in [("Geltendes Recht", CBAM_GESETZ),
                        ("Vorschlag 2026", CBAM_VORSCHLAG)]:
    for ziel_name, ziel in [("Ziel erreicht", True), ("Ziel verfehlt", False)]:
        zeile = [cbam_name, ziel_name]
        for w in WEITERGABE_SZENARIEN:
            _, barwert = rechne(cbam, ziel, w)
            zeile.append(barwert / UNTERNEHMENSWERT * 100)
        ergebnisse.append(zeile)

spalten = ["CBAM-Pfad", "Klimaziel 2050"] + [f"{w:.0%} weiter" for w in WEITERGABE_SZENARIEN]
uebersicht = pd.DataFrame(ergebnisse, columns=spalten)

print(f"\nUnternehmenswert: {UNTERNEHMENSWERT:,} Mio. €")
print("Barwert der CO2-Kosten in % des Unternehmenswerts:\n")
print(uebersicht.round(1).to_string(index=False))
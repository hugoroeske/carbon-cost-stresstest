"""
Monte-Carlo-Simulation: Wie viel Unternehmenswert kosten CO2-Kosten
Heidelberg Materials bis 2050 – und mit welcher Wahrscheinlichkeit?
"""
import os
import numpy as np
import matplotlib.pyplot as plt

# --- Feste Annahmen (wie in co2_kosten.py) ------------------------------
EMISSIONEN_2025 = 22.2       # Mio. t (GB S. 121)
REDUKTION_PRO_JAHR = 0.048   # bis 2030 (GB S. 42)
DECKUNGSGRAD = 1.00          # ETS-Auswertung
PREIS_2025 = 73              # €/t (GB S. 48)
STEUERSATZ = 0.252           # (GB S. 241)
WACC = 0.081                 # (GB S. 248)
UNTERNEHMENSWERT = 25300 + 5715   # Mio. €

CBAM_GESETZ = {2026: .975, 2027: .95, 2028: .90, 2029: .775, 2030: .515,
               2031: .39, 2032: .265, 2033: .14}
CBAM_VORSCHLAG = {2026: .975, 2027: .95, 2028: .915, 2029: .81, 2030: .59,
                  2031: .48, 2032: .375, 2033: .27,
                  2034: .15, 2035: .15, 2036: .15, 2037: .15}

# --- Unsichere Annahmen: Bandbreiten -----------------------------------
ANZAHL = 10_000
rng = np.random.default_rng(seed=42)   # fester Startwert = reproduzierbar

preis_2030 = rng.lognormal(mean=np.log(100), sigma=0.25, size=ANZAHL)
anstieg_ab_2030 = rng.uniform(2, 9, size=ANZAHL)            # €/t pro Jahr
weitergabe = rng.triangular(0.2, 0.4, 0.8, size=ANZAHL)     # Anteil
zielerreichung = rng.uniform(0.3, 1.0, size=ANZAHL)         # Anteil
vorschlag_kommt = rng.random(ANZAHL) < 0.5                  # True/False


def barwert_co2(p2030, anstieg, w, ziel, cbam):
    """Barwert der CO2-Kosten nach Steuern 2026-2050 inkl. Restwert."""
    e2030 = EMISSIONEN_2025 * (1 - REDUKTION_PRO_JAHR) ** 5
    e2050 = e2030 * (1 - ziel)          # Restemissionen 2050
    summe = 0
    for jahr in range(2026, 2051):
        t = jahr - 2025
        if jahr <= 2030:
            e = EMISSIONEN_2025 * (1 - REDUKTION_PRO_JAHR) ** t
            preis = PREIS_2025 + (p2030 - PREIS_2025) / 5 * t
        else:
            e = e2030 + (e2050 - e2030) * (jahr - 2030) / 20
            preis = p2030 + anstieg * (jahr - 2030)
        zukauf = max(e - EMISSIONEN_2025 * DECKUNGSGRAD * cbam.get(jahr, 0), 0)
        nach_steuern = zukauf * preis * (1 - w) * (1 - STEUERSATZ)
        summe += nach_steuern / (1 + WACC) ** t
    # Restwert: Kosten von 2050 laufen ewig weiter (0, wenn Ziel voll erreicht)
    summe += nach_steuern / WACC / (1 + WACC) ** 25
    return summe


# --- 10.000 Durchläufe -------------------------------------------------
ergebnis = np.empty(ANZAHL)
for i in range(ANZAHL):
    cbam = CBAM_VORSCHLAG if vorschlag_kommt[i] else CBAM_GESETZ
    ergebnis[i] = barwert_co2(preis_2030[i], anstieg_ab_2030[i],
                              weitergabe[i], zielerreichung[i], cbam)

anteil = ergebnis / UNTERNEHMENSWERT * 100      # in % des Unternehmenswerts

print(f"\n{ANZAHL:,} Simulationen – Barwert CO2-Kosten in % des Unternehmenswerts")
print(f"Mittelwert:         {anteil.mean():5.1f} %")
print(f"Median:             {np.median(anteil):5.1f} %")
print(f"5 %-Quantil:        {np.percentile(anteil, 5):5.1f} %")
print(f"95 %-Quantil:       {np.percentile(anteil, 95):5.1f} %")
print(f"Wahrsch. > 20 %:    {(anteil > 20).mean():5.1%}")

# --- Histogramm speichern ----------------------------------------------
os.makedirs("ergebnisse", exist_ok=True)
plt.figure(figsize=(8, 4.5))
plt.hist(anteil, bins=60, color="#2a6f97", edgecolor="white")
plt.axvline(np.median(anteil), color="black", linestyle="--",
            label=f"Median {np.median(anteil):.1f} %")
plt.xlabel("Barwert der CO2-Kosten in % des Unternehmenswerts")
plt.ylabel("Anzahl Simulationen")
plt.title("Heidelberg Materials: CO2-Kostenrisiko bis 2050 (10.000 Szenarien)")
plt.legend()
plt.tight_layout()
plt.savefig("ergebnisse/monte_carlo_histogramm.png", dpi=150)
print("\nGrafik gespeichert: ergebnisse/monte_carlo_histogramm.png")
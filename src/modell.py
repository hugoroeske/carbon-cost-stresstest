"""
Kernmodell des CO2-Stresstests: Jahresrechnung, Barwert, Monte Carlo.
Wird von der App (app.py) genutzt. Annahmen und Quellen: annahmen.md
"""
import numpy as np
import pandas as pd

PREIS_2025 = 73   # €/t, Durchschnitt 2025 (GB Heidelberg S. 48)

# Anteil der Gratiszuteilung, der übrig bleibt (CBAM-Faktor); fehlende Jahre = 0
CBAM_PFADE = {
    "Geltendes Recht": {2026: .975, 2027: .95, 2028: .90, 2029: .775, 2030: .515,
                        2031: .39, 2032: .265, 2033: .14},
    "Kommissionsvorschlag 2026": {2026: .975, 2027: .95, 2028: .915, 2029: .81, 2030: .59,
                                  2031: .48, 2032: .375, 2033: .27,
                                  2034: .15, 2035: .15, 2036: .15, 2037: .15},
}

# Je Konzern die festen Annahmen (Werte in Mio. € bzw. Mio. t)
# Je Konzern die festen Annahmen (Werte in Mio. € bzw. Mio. t)
KONZERNE = {
    "Heidelberg Materials": {
        "emissionen_2025": 22.2,      # Länder mit CO2-Preis (GB S. 121)
        "reduktion_bis_2030": 0.048,  # Ziel 512 -> 400 kg/t (GB S. 42)
        "deckungsgrad": 1.00,         # Gratiszuteilung / Emissionen (ETS-Auswertung)
        "steuersatz": 0.252,          # GB S. 241
        "wacc": 0.081,                # GB S. 248
        "rco_2025": 3381,             # GB S. 338
        "boersenwert": 25300,         # onvista, 19.10.2026
        "nettofinanzschulden": 5715,  # GB S. 338
        "pensionen": 624,             # GB S. 57 / Bilanz S. 216
        "pruefspur": "ergebnisse/ki_extraktion_heidelberg.csv",
    },
    "Thyssenkrupp": {
        "emissionen_2025": 17.80,     # ETS 2025 inkl. 50 % HKM (src/ets_thyssenkrupp.py)
        "reduktion_bis_2030": 0.058,  # Ziel Scope 1+2: 21,0 -> 15,6 Mio. t bis 2029/30 (GB S. 123)
        "deckungsgrad": 1.05,         # 18,61 / 17,80 (ETS-Auswertung)
        "steuersatz": 0.316,          # erwarteter Steuersatz Deutschland (GB S. 321)
        "wacc": 0.076,                # nach Steuern, Steel Europe, Test Q4 (GB S. 259)
        "rco_2025": 640,              # bereinigtes EBIT (GB S. 2)
        "boersenwert": 8634,          # 622,5 Mio. Aktien x Kurs
        "nettofinanzschulden": -4862, # negativ = Netto-Finanzguthaben (GB S. 2)
        "pensionen": 5298,            # GB S. 329
        "pruefspur": "ergebnisse/ki_extraktion_thyssenkrupp.csv",
    },
}


def unternehmenswert(k):
    """Börsenwert + Nettofinanzschulden + Pensionen."""
    return k["boersenwert"] + k["nettofinanzschulden"] + k["pensionen"]


def jahresrechnung(k, preis_2030, anstieg, weitergabe, zielerreichung, cbam):
    """Tabelle 2026-2050: Emissionen, Zuteilung, Zukauf, Preis, Kosten, Barwert."""
    e2030 = k["emissionen_2025"] * (1 - k["reduktion_bis_2030"]) ** 5
    e2050 = e2030 * (1 - zielerreichung)
    zeilen = []
    for jahr in range(2026, 2051):
        t = jahr - 2025
        if jahr <= 2030:
            e = k["emissionen_2025"] * (1 - k["reduktion_bis_2030"]) ** t
            preis = PREIS_2025 + (preis_2030 - PREIS_2025) / 5 * t
        else:
            e = e2030 + (e2050 - e2030) * (jahr - 2030) / 20
            preis = preis_2030 + anstieg * (jahr - 2030)
        zuteilung = k["emissionen_2025"] * k["deckungsgrad"] * cbam.get(jahr, 0)
        zukauf = max(e - zuteilung, 0)
        kosten = zukauf * preis * (1 - weitergabe)
        nach_steuern = kosten * (1 - k["steuersatz"])
        zeilen.append({"Jahr": jahr, "Emissionen": e, "Gratiszuteilung": zuteilung,
                       "Zukauf": zukauf, "Preis": preis, "Kosten": kosten,
                       "Nach Steuern": nach_steuern,
                       "Barwert": nach_steuern / (1 + k["wacc"]) ** t})
    return pd.DataFrame(zeilen).set_index("Jahr")


def barwert_gesamt(k, tabelle):
    """Summe der Barwerte plus Restwert (Kosten 2050 als ewige Rente)."""
    restwert = tabelle["Nach Steuern"].iloc[-1] / k["wacc"] / (1 + k["wacc"]) ** 25
    return tabelle["Barwert"].sum() + restwert


def monte_carlo(k, anzahl=10_000, seed=42):
    """Barwert in % des Unternehmenswerts für 10.000 zufällig gezogene Szenarien.
    Rechnet alle Szenarien gleichzeitig (numpy-Arrays) statt einzeln – das ist
    rund 100-mal schneller als eine Schleife über 10.000 Durchläufe."""
    rng = np.random.default_rng(seed)
    preis_2030 = rng.lognormal(np.log(100), 0.25, anzahl)
    anstieg = rng.uniform(2, 9, anzahl)
    weitergabe = rng.triangular(0.2, 0.4, 0.8, anzahl)
    ziel = rng.uniform(0.3, 1.0, anzahl)
    vorschlag = rng.random(anzahl) < 0.5

    e2025 = k["emissionen_2025"]
    e2030 = e2025 * (1 - k["reduktion_bis_2030"]) ** 5
    e2050 = e2030 * (1 - ziel)
    gesetz, kom = CBAM_PFADE["Geltendes Recht"], CBAM_PFADE["Kommissionsvorschlag 2026"]
    summe = np.zeros(anzahl)
    for jahr in range(2026, 2051):
        t = jahr - 2025
        if jahr <= 2030:
            e = e2025 * (1 - k["reduktion_bis_2030"]) ** t
            preis = PREIS_2025 + (preis_2030 - PREIS_2025) / 5 * t
        else:
            e = e2030 + (e2050 - e2030) * (jahr - 2030) / 20
            preis = preis_2030 + anstieg * (jahr - 2030)
        faktor = np.where(vorschlag, kom.get(jahr, 0), gesetz.get(jahr, 0))
        zukauf = np.maximum(e - e2025 * k["deckungsgrad"] * faktor, 0)
        nach_steuern = zukauf * preis * (1 - weitergabe) * (1 - k["steuersatz"])
        summe += nach_steuern / (1 + k["wacc"]) ** t
    summe += nach_steuern / k["wacc"] / (1 + k["wacc"]) ** 25   # Restwert
    return summe / unternehmenswert(k) * 100
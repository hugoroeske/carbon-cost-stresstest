"""
Kernmodell des CO2-Stresstests: Jahresrechnung, Barwert, Monte Carlo.
Wird von der App (app.py) genutzt. Annahmen und Quellen: annahmen.md
"""
import glob
import json
import os

import numpy as np
import pandas as pd

PREIS_2025 = 73   # €/t, Durchschnitt EU-ETS 2025 (Instrat: 73,43 €/t, volumengewichtet)

# Anteil der Gratiszuteilung, der übrig bleibt (CBAM-Faktor); fehlende Jahre = 0
CBAM_PFADE = {
    "Geltendes Recht": {2026: .975, 2027: .95, 2028: .90, 2029: .775, 2030: .515,
                        2031: .39, 2032: .265, 2033: .14},
    "Kommissionsvorschlag 2026": {2026: .975, 2027: .95, 2028: .915, 2029: .81, 2030: .59,
                                  2031: .48, 2032: .375, 2033: .27,
                                  2034: .15, 2035: .15, 2036: .15, 2037: .15},
}

# Je Konzern die festen Annahmen (Werte in Mio. € bzw. Mio. t).
# Weitere Konzerne liegen als JSON-Dateien in konzerne/ bzw. lokal/ (lokal/ ist nicht im Repo).
KONZERNE = {
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


# Konzerne, die über die Upload-Seite gespeichert wurden (je Konzern eine JSON-Datei)
KONZERN_ORDNER = os.path.join(os.path.dirname(__file__), "..", "konzerne")
# Konzerne, die nur auf dem eigenen Rechner erscheinen sollen (Ordner lokal/ ist nicht im Repo)
LOKAL_ORDNER = os.path.join(os.path.dirname(__file__), "..", "lokal")


def konzerne_laden(ordner=KONZERN_ORDNER):
    """Liest alle gespeicherten Konzerne und bringt sie in dasselbe Format wie KONZERNE.
    Leere oder kaputte Dateien werden übersprungen statt die App abstürzen zu lassen."""
    geladen = {}
    for pfad in sorted(glob.glob(os.path.join(ordner, "*.json"))):
        try:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            k = {schluessel: eintrag["wert"] for schluessel, eintrag in daten["parameter"].items()}
            k["pruefspur"] = daten.get("pruefspur", "")
        except (json.JSONDecodeError, KeyError, TypeError):
            print(f"Übersprungen (kein gültiger Konzern): {pfad}")
            continue
        name = daten.get("name", os.path.basename(pfad))
        if name in KONZERNE:              # fest eingetragene Konzerne nie überschreiben
            name += " (Upload)"
        geladen[name] = k
    return geladen


def alle_konzerne():
    """Fest eingetragene plus gespeicherte Konzerne. Wird bei jedem Neuladen der Seite
    aufgerufen, damit ein frisch gespeicherter Konzern sofort auswählbar ist."""
    return {**KONZERNE, **konzerne_laden(), **konzerne_laden(LOKAL_ORDNER)}


JAHRE = range(2026, 2051)

# Unternehmensszenarien: diese Werte verändern das Ergebnis nicht (Basisfall)
NEUTRAL = {"verzoegerung_jahre": 0, "anteil_bepreist": 1.0,
           "abspaltung_emissionen": 0.0, "abspaltung_wert": 0.0}


def szenario_anwenden(k, szenario=None):
    """Gibt eine KOPIE der Konzerndaten mit angewendetem Szenario zurück.
    Die gespeicherten Werte in KONZERNE bleiben dadurch unverändert."""
    s = {**NEUTRAL, **(szenario or {})}
    neu = dict(k)
    # Nur bepreiste Emissionen zählen; ein abgespaltenes Segment nimmt seine
    # Emissionen (und anteilig seine Gratiszuteilung) mit
    neu["emissionen_2025"] = (k["emissionen_2025"] * s["anteil_bepreist"]
                              * (1 - s["abspaltung_emissionen"]))
    neu["verzoegerung_jahre"] = s["verzoegerung_jahre"]
    neu["wertanteil"] = 1 - s["abspaltung_wert"]
    return neu


def unternehmenswert(k):
    """(Börsenwert + Nettofinanzschulden + Pensionen) x verbleibender Wertanteil."""
    basis = k["boersenwert"] + k["nettofinanzschulden"] + k["pensionen"]
    return basis * k.get("wertanteil", 1.0)


def emissionspfad(k, zielerreichung):
    """Emissionen 2026-2050 (Liste, ein Eintrag je Jahr). Wird von jahresrechnung,
    monte_carlo und tornado gemeinsam genutzt. Bei Monte Carlo ist zielerreichung
    ein Array, dann ist jeder Eintrag ab 2031 ebenfalls ein Array."""
    e2025 = k["emissionen_2025"]
    r = k["reduktion_bis_2030"]
    e2030 = e2025 * (1 - r) ** 5
    e2050 = e2030 * (1 - zielerreichung)
    pfad = []
    for jahr in JAHRE:
        # Jahre seit Beginn der Reduktion; bei Verzögerung bleibt es erst bei 2025
        t = max(jahr - 2025 - k.get("verzoegerung_jahre", 0), 0)
        if t <= 5:
            pfad.append(e2025 * (1 - r) ** t)
        else:
            pfad.append(e2030 + (e2050 - e2030) * (t - 5) / 20)
    return pfad


def jahresrechnung(k, preis_2030, anstieg, weitergabe, zielerreichung, cbam):
    """Tabelle 2026-2050: Emissionen, Zuteilung, Zukauf, Preis, Kosten, Barwert."""
    pfad = emissionspfad(k, zielerreichung)
    zeilen = []
    for jahr, e in zip(JAHRE, pfad):
        t = jahr - 2025
        if jahr <= 2030:
            preis = PREIS_2025 + (preis_2030 - PREIS_2025) / 5 * t
        else:
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


def annahmen_ziehen(anzahl=10_000, seed=42):
    """Zieht die unsicheren Annahmen zufällig. Monte Carlo und Tornado nutzen
    dieselben Ziehungen, damit beide auf denselben Verteilungen beruhen."""
    rng = np.random.default_rng(seed)
    return {
        "preis_2030": rng.lognormal(np.log(100), 0.25, anzahl),
        "anstieg": rng.uniform(2, 9, anzahl),
        "weitergabe": rng.triangular(0.2, 0.4, 0.8, anzahl),
        "ziel": rng.uniform(0.3, 1.0, anzahl),
        "vorschlag": rng.random(anzahl) < 0.5,
    }


def monte_carlo(k, anzahl=10_000, seed=42):
    """Barwert in % des Unternehmenswerts für 10.000 zufällig gezogene Szenarien.
    Rechnet alle Szenarien gleichzeitig (numpy-Arrays) statt einzeln – das ist
    rund 100-mal schneller als eine Schleife über 10.000 Durchläufe."""
    z = annahmen_ziehen(anzahl, seed)
    preis_2030, anstieg = z["preis_2030"], z["anstieg"]
    weitergabe, ziel, vorschlag = z["weitergabe"], z["ziel"], z["vorschlag"]

    e2025 = k["emissionen_2025"]
    pfad = emissionspfad(k, ziel)
    gesetz, kom = CBAM_PFADE["Geltendes Recht"], CBAM_PFADE["Kommissionsvorschlag 2026"]
    summe = np.zeros(anzahl)
    for jahr, e in zip(JAHRE, pfad):
        t = jahr - 2025
        if jahr <= 2030:
            preis = PREIS_2025 + (preis_2030 - PREIS_2025) / 5 * t
        else:
            preis = preis_2030 + anstieg * (jahr - 2030)
        faktor = np.where(vorschlag, kom.get(jahr, 0), gesetz.get(jahr, 0))
        zukauf = np.maximum(e - e2025 * k["deckungsgrad"] * faktor, 0)
        nach_steuern = zukauf * preis * (1 - weitergabe) * (1 - k["steuersatz"])
        summe += nach_steuern / (1 + k["wacc"]) ** t
    summe += nach_steuern / k["wacc"] / (1 + k["wacc"]) ** 25   # Restwert
    return summe / unternehmenswert(k) * 100


def tornado(k):
    """Sensitivität: alle Annahmen auf ihren Median, dann jeweils EINE Annahme
    auf ihr 5-%- bzw. 95-%-Quantil. Ergebnis in % des Unternehmenswerts."""
    z = annahmen_ziehen()
    basis = {"preis_2030": np.median(z["preis_2030"]), "anstieg": np.median(z["anstieg"]),
             "weitergabe": np.median(z["weitergabe"]), "zielerreichung": np.median(z["ziel"]),
             "cbam": CBAM_PFADE["Geltendes Recht"]}

    def in_prozent(**aenderung):
        werte = {**basis, **aenderung}
        tabelle = jahresrechnung(k, werte["preis_2030"], werte["anstieg"], werte["weitergabe"],
                                 werte["zielerreichung"], werte["cbam"])
        return barwert_gesamt(k, tabelle) / unternehmenswert(k) * 100

    tests = [("Carbon price 2030", "preis_2030", z["preis_2030"]),
             ("Price increase after 2030", "anstieg", z["anstieg"]),
             ("Pass-through to customers", "weitergabe", z["weitergabe"]),
             ("Climate target achieved", "zielerreichung", z["ziel"])]
    zeilen = []
    for name, schluessel, werte in tests:
        niedrig, hoch = np.percentile(werte, [5, 95])
        a, b = in_prozent(**{schluessel: niedrig}), in_prozent(**{schluessel: hoch})
        zeilen.append({"Annahme": name, "Tief": min(a, b), "Hoch": max(a, b)})
    a = in_prozent(cbam=CBAM_PFADE["Kommissionsvorschlag 2026"])
    b = in_prozent()
    zeilen.append({"Annahme": "CBAM path", "Tief": min(a, b), "Hoch": max(a, b)})

    ergebnis = pd.DataFrame(zeilen)
    ergebnis["Spanne"] = ergebnis["Hoch"] - ergebnis["Tief"]
    return ergebnis.sort_values("Spanne").reset_index(drop=True), in_prozent()

# ======================================================================
# Ranking: alle Konzerne mit EINHEITLICHEN Annahmen vergleichen
# ======================================================================
RANKING_DATEI = os.path.join(os.path.dirname(__file__), "ranking_daten.json")
RANKING_LOKAL = os.path.join(LOKAL_ORDNER, "ranking_lokal.json")

EINHEITLICH = {"wacc": 0.08, "steuersatz": 0.25, "reduktion_bis_2030": 0.0, "preis_2030": 100,
               "anstieg": 5.4, "weitergabe": 0.40, "zielerreichung": 0.65, "cbam": "Geltendes Recht"}


def ranking_laden():
    """Daten für das Ranking: öffentliche Datei im Repo plus (falls vorhanden) lokale Datei."""
    daten = {}
    for pfad in (RANKING_DATEI, RANKING_LOKAL):
        if os.path.exists(pfad):
            with open(pfad, encoding="utf-8") as f:
                daten.update(json.load(f)["konzerne"])
    return daten


def ranking(daten, **aenderung):
    """Barwert der zusätzlichen CO2-Kosten je Konzern bei gleichen Annahmen für alle.
    Emissionen bleiben bis 2030 auf dem Stand 2025 (keine Firmenpläne), damit nur
    das heutige CO2-Risiko verglichen wird."""
    a = {**EINHEITLICH, **aenderung}
    zeilen = []
    for name, x in daten.items():
        k = {"emissionen_2025": x["emissionen_2025"], "deckungsgrad": x["deckungsgrad"],
             "reduktion_bis_2030": a["reduktion_bis_2030"], "steuersatz": a["steuersatz"],
             "wacc": a["wacc"]}
        tabelle = jahresrechnung(k, a["preis_2030"], a["anstieg"], a["weitergabe"],
                                 a["zielerreichung"], CBAM_PFADE[a["cbam"]])
        barwert = barwert_gesamt(k, tabelle)
        zukauf = tabelle["Zukauf"]
        erstes_jahr = int(zukauf[zukauf > 0].index.min()) if (zukauf > 0).any() else None
        uw = None
        if "boersenwert" in x:
            uw = x["boersenwert"] + x["nettofinanzschulden"] + x["pensionen"]
        zeilen.append({"Konzern": name, "Branche": x["branche"],
                       "Emissionen 2025 (Mt)": x["emissionen_2025"],
                       "Deckungsgrad": x["deckungsgrad"], "Erster Zukauf": erstes_jahr,
                       "Barwert CO2 (Mrd. €)": barwert / 1000,
                       "Unternehmenswert (Mrd. €)": uw / 1000 if uw else None,
                       "Anteil am Unternehmenswert": barwert / uw if uw else None,
                       "Anteil unsicher zugeordnet": x["anteil_unsicher"]})
    ergebnis = pd.DataFrame(zeilen).sort_values(["Anteil am Unternehmenswert", "Barwert CO2 (Mrd. €)"],
                                                ascending=False, na_position="last")
    ergebnis.insert(0, "Rang", range(1, len(ergebnis) + 1))
    return ergebnis.reset_index(drop=True)

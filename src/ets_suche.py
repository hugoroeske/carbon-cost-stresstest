"""
EU-ETS-Register durchsuchen: passende Anlagen finden, die von Hand bestätigte
Auswahl zusammenfassen und gegen den berichteten Scope-1-Wert abstimmen.
Die Zuordnung trifft immer der Mensch – die App schlägt nur Kandidaten vor.
"""
import pandas as pd

DATEI = "data/raw/ets_2025.xlsx"
ZUTEILUNG_SPALTEN = ["ALLOCATION_2025", "ALLOCATION_RESERVE_2025", "ALLOCATION_TRANSITIONAL_2025"]
ZAHLEN_SPALTEN = ZUTEILUNG_SPALTEN + ["VERIFIED_EMISSIONS_2025", "VERIFIED_EMISSIONS_2024"]


def register_laden(datei=DATEI):
    """Liest das Register (Kopfzeile = Zeile mit 'REGISTRY_CODE'), nur offene Anlagen."""
    roh = pd.read_excel(datei, sheet_name="data", header=None)
    roh = roh.map(lambda x: x.strip() if isinstance(x, str) else x)
    kopf = (roh == "REGISTRY_CODE").any(axis=1).idxmax()
    df = roh.iloc[kopf + 1:].copy()
    df.columns = roh.iloc[kopf]
    df.columns.name = None
    df = df[df["ACCOUNT_CLOSURE"].astype(str).str.upper() == "OPEN"].copy()
    for s in ZAHLEN_SPALTEN:
        df[s] = pd.to_numeric(df[s], errors="coerce").fillna(0)
    # Doppelte Leerzeichen vereinheitlichen ("Kraftwerk  Hamborn" -> "Kraftwerk Hamborn")
    df["NAME"] = df["INSTALLATION_NAME"].astype(str).str.replace(r"\s+", " ", regex=True)
    df["KONTO"] = df["IDENTIFIER_IN_REG"].astype(str).str.replace(r"\s+", " ", regex=True)
    df["ZUTEILUNG"] = df[ZUTEILUNG_SPALTEN].sum(axis=1)
    return df


def anlagen_suchen(register, begriffe):
    """Alle Anlagen, deren Konto- oder Anlagenname einen der Begriffe enthält."""
    text = (register["KONTO"] + " | " + register["NAME"]).str.lower()
    treffer = pd.Series(False, index=register.index)
    for begriff in begriffe:
        if begriff.strip():
            treffer |= text.str.contains(begriff.strip().lower(), regex=False)
    gefunden = register[treffer]
    return pd.DataFrame({
        "Aufnehmen": False,
        "Anteil": 1.0,
        "Standort": "",
        "Land": gefunden["REGISTRY_CODE"],
        "Konto": gefunden["KONTO"],
        "Anlage": gefunden["NAME"],
        "Tätigkeit": gefunden["MAIN_ACTIVITY_TYPE_CODE"].astype(str),
        "Emissionen 2025 (t)": gefunden["VERIFIED_EMISSIONS_2025"],
        "Emissionen 2024 (t)": gefunden["VERIFIED_EMISSIONS_2024"],
        "Zuteilung 2025 (t)": gefunden["ZUTEILUNG"],
    }).sort_values("Emissionen 2025 (t)", ascending=False).reset_index(drop=True)


def zusammenfassen(auswahl, scope1=None):
    """Summen der angehakten Anlagen (mit Anteil gewichtet) in Mio. t,
    Deckungsgrad und Abweichung zum berichteten Scope 1 in %."""
    gewaehlt = auswahl[auswahl["Aufnehmen"]]
    anteil = gewaehlt["Anteil"]
    e25 = float((gewaehlt["Emissionen 2025 (t)"] * anteil).sum()) / 1e6
    e24 = float((gewaehlt["Emissionen 2024 (t)"] * anteil).sum()) / 1e6
    zut = float((gewaehlt["Zuteilung 2025 (t)"] * anteil).sum()) / 1e6
    ergebnis = {"anzahl": len(gewaehlt), "emissionen_2025": e25, "emissionen_2024": e24,
                "zuteilung_2025": zut, "deckungsgrad": zut / e25 if e25 > 0 else None,
                "abweichung_2025": None, "abweichung_2024": None}
    if scope1:
        ergebnis["abweichung_2025"] = (e25 / scope1 - 1) * 100
        ergebnis["abweichung_2024"] = (e24 / scope1 - 1) * 100
    return ergebnis

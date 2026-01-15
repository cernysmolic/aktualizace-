import pdfplumber
import pandas as pd
import re
from collections import defaultdict
from pathlib import Path

# =====================
# POVOLENÉ ROZMĚRY PRO POVLEČENÍ (6 SLOUPCŮ)
# =====================
POVLECENI_ROZMERY = [
    "70/90",
    "50/70",
    "140/200",
    "140/220",
    "200/220"
]

# =====================
# NASTAVENÍ SKLADU
# =====================
NAZEV_SKLADU_SOUBORU = "STAV_SKLADU.xlsx"
VYSTUP_SKLAD_PO_ODECTU = "STAV_SKLADU_PO_ODECTU.xlsx"

# Sloupce ve skladové tabulce:
# B = název z PDF
# D = aktuální stav
# E = stav po odečtu
SKLAD_COL_NAZEV = "PDF_NAZEV"     # my si ho vytvoříme
SKLAD_COL_STAV = "STAV"           # my si ho vytvoříme
SKLAD_COL_PO = "STAV_PO_ODECTU"   # my si ho vytvoříme


def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("–", "-").replace("—", "-")
    return s


def zpracuj_pdf(cesta_k_pdf: str):
    pdf_path = Path(cesta_k_pdf)
    vystup_slozka = pdf_path.parent  # temp/

    data = defaultdict(lambda: defaultdict(int))

    # =====================
    # POMOCNÉ FUNKCE
    # =====================
    def sestav_radky(words, tolerance=3):
        radky = {}
        for w in words:
            y = round(w["top"] / tolerance) * tolerance
            radky.setdefault(y, []).append(w["text"])
        return [" ".join(radky[y]).strip() for y in sorted(radky)]

    def analyzuj_nazev(nazev):
        m = re.search(r"\b(\d+)\s*ks\b", nazev, flags=re.I)
        baleni_ks = int(m.group(1)) if m else 1

        cisty = re.sub(r"\b\d+\s*ks\b", "", nazev, flags=re.I)
        cisty = re.sub(r"\d+,\d+\s*€.*", "", cisty)
        return cisty.strip(), baleni_ks

    def zpracuj_rozmery(radek, mnozstvi):
        """
        POVLEČENÍ SETY:
        Když PDF řekne "2 ks" a variant je "1x 70/90 + 1x 140/200",
        tak reálně je to:
        2x 70/90 a 2x 140/200
        """
        vysledek = defaultdict(int)

        # explicitní: 1x 70/90
        for p, r in re.findall(r"(\d+)x\s*(\d+/\d+)", radek):
            # tady je p většinou 1
            vysledek[r] += int(p) * int(mnozstvi)

        if vysledek:
            return vysledek

        # fallback: jen rozmery bez 1x
        for r in re.findall(r"(\d+/\d+)", radek):
            vysledek[r] += int(mnozstvi)

        return vysledek

    # =====================
    # ČTENÍ PDF
    # =====================
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            radky = sestav_radky(page.extract_words() or [])

            typ = None
            nazev = ""
            baleni_ks = 1
            mnozstvi = 1

            for r in radky:
                r_low = r.lower()

                if r_low.startswith((
                    "bavlnené", "mušelínové", "saténové",
                    "krepové", "mikroplyšové",
                    "prestieradlo", "chránič",
                    "ručník", "osuška", "uterák",
                    "paplón", "paplon",
                    "ubrus", "deka", "vankúš",
                    "saunové", "utěrky", "pleny", "plátno"
                )):
                    m = re.search(r"\b(\d+)\s*ks\b", r)
                    mnozstvi = int(m.group(1)) if m else 1

                    typ = r.strip()
                    nazev = ""
                    baleni_ks = 1

                    if " - " in r:
                        typ, raw = r.split(" - ", 1)
                        typ = typ.strip()
                        nazev, baleni_ks = analyzuj_nazev(raw)

                elif "rozmery" in r_low and typ:
                    rozpis = zpracuj_rozmery(r, mnozstvi)
                    for rozmer, ks in rozpis.items():
                        data[(typ, nazev, baleni_ks)][rozmer] += ks

    # =====================
    # DATAFRAME – VŠE
    # =====================
    radky_out = []
    for (typ, nazev, baleni_ks), hodnoty in data.items():
        row = {
            "Typ produktu": suggest_clean_type(typ),
            "Název": nazev,
            "Balení (ks)": baleni_ks
        }
        for r, v in hodnoty.items():
            row[r] = v
        radky_out.append(row)

    df = pd.DataFrame(radky_out).fillna(0)
    if not df.empty:
        df = df.sort_values(by=["Typ produktu", "Název"])

    # =====================
    # POVLEČENÍ – POUZE 6 SLOUPCŮ
    # =====================
    df_povleceni = df[df["Typ produktu"].str.contains("obliečky", case=False, na=False)]

    zaklad = ["Typ produktu", "Název", "Balení (ks)"]
    rozmery_existujici = [r for r in POVLECENI_ROZMERY if r in df_povleceni.columns]

    if not df_povleceni.empty:
        df_povleceni = df_povleceni[zaklad + rozmery_existujici]

        df_povleceni["CELKEM"] = df_povleceni[rozmery_existujici].sum(axis=1)

        souctovy = {
            "Typ produktu": "CELKEM",
            "Název": "",
            "Balení (ks)": ""
        }
        for r in rozmery_existujici:
            souctovy[r] = df_povleceni[r].sum()
        souctovy["CELKEM"] = df_povleceni["CELKEM"].sum()

        df_povleceni = pd.concat(
            [df_povleceni, pd.DataFrame([souctovy])],
            ignore_index=True
        )

    # =====================
    # OSTATNÍ SORTIMENT
    # =====================
    df_ostatni = df[~df["Typ produktu"].str.contains("obliečky", case=False, na=False)]

    # =====================
    # ULOŽENÍ SOUPISŮ
    # =====================
    soubor_povleceni = vystup_slozka / "soupis_povleceni.xlsx"
    soubor_ostatni = vystup_slozka / "soupis_ostatni_sortiment.xlsx"

    df_povleceni.to_excel(soubor_povleceni, index=False, engine="openpyxl")
    df_ostatni.to_excel(soubor_ostatni, index=False, engine="openpyxl")

    # =====================
    # ODEČET ZE SKLADU
    # =====================
    sklad_path = vystup_slozka / NAZEV_SKLADU_SOUBORU
    sklad_vystup = vystup_slozka / VYSTUP_SKLAD_PO_ODECTU

    if sklad_path.exists() and not df_povleceni.empty:
        sklad_df = pd.read_excel(sklad_path, engine="openpyxl")

        # Očekávání: sloupec B = názvy z PDF, sloupec D = stav
        # přemapujeme je na názvy, aby to bylo jasné
        # (pozor, pandas indexuje sloupce podle jmen, ne písmen)
        # Pokud tabulka nemá hlavičku, tak musíme vzít podle pozice.
        if sklad_df.columns.size < 5:
            # když je to "divné", radši stop
            raise Exception("STAV_SKLADU.xlsx nemá dost sloupců (musí mít minimálně A–E).")

        # Vezmeme B (index 1) a D (index 3)
        sklad_df[SKLAD_COL_NAZEV] = sklad_df.iloc[:, 1].astype(str)
        sklad_df[SKLAD_COL_STAV] = pd.to_numeric(sklad_df.iloc[:, 3], errors="coerce").fillna(0).astype(int)

        sklad_df[SKLAD_COL_PO] = sklad_df[SKLAD_COL_STAV].copy()

        # soupis objednávek: odečítáme jen povlečení (bez CELKEM řádku)
        objednavky = df_povleceni.copy()
        objednavky = objednavky[objednavky["Typ produktu"] != "CELKEM"]

        # odečítáme pro každý produkt a rozměr
        for _, row in objednavky.iterrows():
            nazev_obj = normalize_text(row["Název"])

            for rozmer in rozmery_existujici:
                odebrat = int(row.get(rozmer, 0))

                if odebrat <= 0:
                    continue

                # najdi ve skladu stejný název (sloupec B)
                mask = sklad_df[SKLAD_COL_NAZEV].apply(normalize_text) == nazev_obj

                if mask.any():
                    # odečti ze sloupce E (STAV_PO_ODECTU)
                    sklad_df.loc[mask, SKLAD_COL_PO] = sklad_df.loc[mask, SKLAD_COL_PO] - odebrat

        # zapíšeme do sloupce E (index 4)
        sklad_df.iloc[:, 4] = sklad_df[SKLAD_COL_PO]

        sklad_df.to_excel(sklad_vystup, index=False, engine="openpyxl")

    return {
        "povleceni": soubor_povleceni,
        "ostatni": soubor_ostatni,
        "sklad_po_odecku": sklad_vystup if sklad_path.exists() else None
    }


def suggest_clean_type(typ: str) -> str:
    # jen drobné čištění
    if not isinstance(typ, str):
        return ""
    return typ.strip()






import pdfplumber
import pandas as pd
import re
from collections import defaultdict
from pathlib import Path


def zpracuj_pdf(cesta_k_pdf: str):
    pdf_path = Path(cesta_k_pdf)
    vystup_slozka = pdf_path.parent  # temp/

    data = defaultdict(lambda: defaultdict(int))
    vsechny_rozmery = set()

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
        vysledek = defaultdict(int)
        for p, r in re.findall(r"(\d+)x\s*(\d+/\d+)", radek):
            vysledek[r] += int(p)
        if vysledek:
            return vysledek
        for r in re.findall(r"(\d+/\d+)", radek):
            vysledek[r] += mnozstvi
        return vysledek

    # =====================
    # ČTENÍ PDF
    # =====================
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            radky = sestav_radky(page.extract_words() or [])

            typ = None
            nazev = None
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
                        vsechny_rozmery.add(rozmer)

    # =====================
    # DATAFRAME
    # =====================
    sloupce = ["Typ produktu", "Název", "Balení (ks)"] + sorted(vsechny_rozmery)
    radky_out = []

    for (typ, nazev, baleni_ks), hodnoty in data.items():
        row = {
            "Typ produktu": typ,
            "Název": nazev,
            "Balení (ks)": baleni_ks
        }
        for r in vsechny_rozmery:
            row[r] = hodnoty.get(r, 0)
        radky_out.append(row)

    df = pd.DataFrame(radky_out, columns=sloupce)
    df = df.sort_values(by=["Typ produktu", "Název"])

    # =====================
    # ROZDĚLENÍ
    # =====================
    df_povleceni = df[df["Typ produktu"].str.contains("obliečky", case=False, na=False)]
    df_ostatni = df[~df["Typ produktu"].str.contains("obliečky", case=False, na=False)]

    # =====================
    # SOUČTOVÝ ŘÁDEK – POVLEČENÍ
    # =====================
    if not df_povleceni.empty:
        soucty = df_povleceni.select_dtypes(include="number").sum()
        souctovy_radek = {
            "Typ produktu": "CELKEM",
            "Název": "",
            "Balení (ks)": ""
        }
        souctovy_radek.update(soucty)

        df_povleceni = pd.concat(
            [df_povleceni, pd.DataFrame([souctovy_radek])],
            ignore_index=True
        )

    # =====================
    # ULOŽENÍ
    # =====================
    soubor_vse = vystup_slozka / "soupis_skladovy.xlsx"
    soubor_povleceni = vystup_slozka / "soupis_povleceni.xlsx"
    soubor_ostatni = vystup_slozka / "soupis_ostatni_sortiment.xlsx"

    df.to_excel(soubor_vse, index=False, engine="openpyxl")
    df_povleceni.to_excel(soubor_povleceni, index=False, engine="openpyxl")
    df_ostatni.to_excel(soubor_ostatni, index=False, engine="openpyxl")

    return {
        "povleceni": soubor_povleceni,
        "ostatni": soubor_ostatni
    }

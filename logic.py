import pdfplumber
import pandas as pd
import re
from collections import defaultdict
from pathlib import Path

POVLECENI_ROZMERY = ["70/90", "50/70", "140/200", "140/220", "200/220"]


def zpracuj_pdf(cesta_k_pdf: str, cesta_sklad: str):
    pdf_path = Path(cesta_k_pdf)
    sklad_path = Path(cesta_sklad)
    vystup_slozka = pdf_path.parent

    data = defaultdict(lambda: defaultdict(int))

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
    # 1) ČTENÍ PDF
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

                    # ❗ U POVLEČENÍ: "2 ks" znamená 2 SETY -> 2x polštář + 2x peřina
                    if "obliečky" in typ.lower():
                        for rozmer in list(rozpis.keys()):
                            rozpis[rozmer] *= mnozstvi

                    for rozmer, ks in rozpis.items():
                        data[(typ, nazev, baleni_ks)][rozmer] += ks

    # =====================
    # 2) VÝSTUP OBJEDNÁVEK
    # =====================
    radky_out = []
    for (typ, nazev, baleni_ks), hodnoty in data.items():
        row = {"Typ produktu": typ, "Název": nazev, "Balení (ks)": baleni_ks}
        for r, v in hodnoty.items():
            row[r] = v
        radky_out.append(row)

    df = pd.DataFrame(radky_out).fillna(0)
    df = df.sort_values(by=["Typ produktu", "Název"])

    df_povleceni = df[df["Typ produktu"].str.contains("obliečky", case=False, na=False)]
    df_ostatni = df[~df["Typ produktu"].str.contains("obliečky", case=False, na=False)]

    zaklad = ["Typ produktu", "Název", "Balení (ks)"]
    rozmery_existujici = [r for r in POVLECENI_ROZMERY if r in df_povleceni.columns]

    if not df_povleceni.empty:
        df_povleceni = df_povleceni[zaklad + rozmery_existujici]
        df_povleceni["CELKEM"] = df_povleceni[rozmery_existujici].sum(axis=1)

    soubor_povleceni = vystup_slozka / "soupis_povleceni.xlsx"
    soubor_ostatni = vystup_slozka / "soupis_ostatni_sortiment.xlsx"

    df_povleceni.to_excel(soubor_povleceni, index=False, engine="openpyxl")
    df_ostatni.to_excel(soubor_ostatni, index=False, engine="openpyxl")

    # =====================
    # 3) ODEČET ZE SKLADU
    # =====================
    sklad_df = pd.read_excel(sklad_path, engine="openpyxl")

    # očekávání: B = názvy z PDF, D = aktuální stav, E = nový stav
    # pandas index: A=0, B=1, C=2, D=3, E=4
    for i in range(len(sklad_df)):
        nazev_pdf = str(sklad_df.iloc[i, 1]).strip()  # sloupec B
        if nazev_pdf == "" or nazev_pdf.lower() == "nan":
            continue

        # kolik se prodalo z PDF (součet přes rozměry)
        prodano = 0

        # najdi odpovídající řádek v df_povleceni podle názvu
        match = df_povleceni[df_povleceni["Název"].str.contains(nazev_pdf, case=False, na=False)]

        if not match.empty:
            # sečteme rozměry
            for r in rozmery_existujici:
                prodano += int(match.iloc[0][r])

        aktualni = sklad_df.iloc[i, 3]  # sloupec D
        try:
            aktualni = int(aktualni)
        except:
            aktualni = 0

        novy = aktualni - prodano
        sklad_df.iloc[i, 4] = novy  # sloupec E

    soubor_sklad = vystup_slozka / "stav_skladu_po_odectu.xlsx"
    sklad_df.to_excel(soubor_sklad, index=False, engine="openpyxl")

    return {
        "povleceni": soubor_povleceni,
        "ostatni": soubor_ostatni,
        "sklad": soubor_sklad
    }






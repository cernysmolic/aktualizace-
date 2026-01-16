import pdfplumber
import pandas as pd
import re
from collections import defaultdict
from pathlib import Path

# Povolené rozměry (jen pro výstup do Excelu)
POVLECENI_ROZMERY = ["70/90", "50/70", "140/200", "140/220", "200/220"]


def zpracuj_pdf(cesta_k_pdf: str, cesta_sklad: str):
    pdf_path = Path(cesta_k_pdf)
    sklad_path = Path(cesta_sklad)
    vystup_slozka = pdf_path.parent

    # data: (typ, nazev, baleni) -> rozmery -> kusy komponent
    data = defaultdict(lambda: defaultdict(int))

    # sety: (typ, nazev, baleni) -> počet setů (množství z PDF)
    sety = defaultdict(int)

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

    def zpracuj_rozmery(radek):
        """
        Vrací rozměry v řádku.
        Pokud je tam "1x 70/90 + 1x 140/200", tak vrátí {70/90:1, 140/200:1}
        Pokud tam není x, tak vrátí {rozmer:1}
        """
        vysledek = defaultdict(int)

        # např. 1x 70/90
        for p, r in re.findall(r"(\d+)x\s*(\d+/\d+)", radek):
            vysledek[r] += int(p)

        if vysledek:
            return vysledek

        # běžný zápis: Rozmery: 70/90
        for r in re.findall(r"(\d+/\d+)", radek):
            vysledek[r] += 1

        return vysledek

    def normalizuj_text(s: str) -> str:
        if s is None:
            return ""
        s = str(s).strip()
        s = re.sub(r"\s+", " ", s)
        return s

    def normalizuj_alias(alias_text: str) -> str:
        """
        Alias ve skladu může obsahovat i Variant.
        Chceme jen název produktu bez Variant části.
        """
        s = normalizuj_text(alias_text)
        if not s:
            return ""

        # uříznout Variant část
        s = re.split(r"\bvariant\b\s*:", s, flags=re.I)[0].strip()
        s = re.sub(r"\s+", " ", s).strip()
        return s

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

                # zachytíme produktový řádek
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

                    # pokud je to povlečení, bereme množství jako SETY
                    if typ and "obliečky" in typ.lower():
                        sety[(typ, nazev, baleni_ks)] += int(mnozstvi)

                # zachytíme řádek s rozměry
                elif "rozmery" in r_low and typ:
                    rozpis = zpracuj_rozmery(r)

                    # Povlečení: 1 set = 1x polštář + 1x peřina
                    # takže rozměry násobíme počtem setů
                    if "obliečky" in typ.lower():
                        for rozmer in list(rozpis.keys()):
                            rozpis[rozmer] = int(rozpis[rozmer]) * int(mnozstvi)

                    for rozmer, ks in rozpis.items():
                        data[(typ, nazev, baleni_ks)][rozmer] += int(ks)

    # =====================
    # 2) VÝSTUP OBJEDNÁVEK
    # =====================
    radky_out = []
    for (typ, nazev, baleni_ks), hodnoty in data.items():
        row = {
            "Typ produktu": typ,
            "Název": nazev,
            "Balení (ks)": baleni_ks,
        }

        # rozměry do sloupců
        for r in POVLECENI_ROZMERY:
            row[r] = int(hodnoty.get(r, 0))

        # přidáme SETY (počet objednaných kusů z PDF)
        row["SETY"] = int(sety.get((typ, nazev, baleni_ks), 0))

        # CELKEM komponent
        row["CELKEM_KOMPONENT"] = sum(int(v) for v in hodnoty.values())

        radky_out.append(row)

    df = pd.DataFrame(radky_out).fillna(0)

    # rozdělení na povlečení / ostatní
    df_povleceni = df[df["Typ produktu"].str.contains("obliečky", case=False, na=False)]
    df_ostatni = df[~df["Typ produktu"].str.contains("obliečky", case=False, na=False)]

    # uložit soupisy
    soubor_povleceni = vystup_slozka / "soupis_povleceni.xlsx"
    soubor_ostatni = vystup_slozka / "soupis_ostatni_sortiment.xlsx"

    df_povleceni.to_excel(soubor_povleceni, index=False, engine="openpyxl")
    df_ostatni.to_excel(soubor_ostatni, index=False, engine="openpyxl")

    # =====================
    # 3) ODEČET ZE SKLADU (ODEČÍTÁME SETY)
    # =====================
    sklad_df = pd.read_excel(sklad_path, engine="openpyxl")

    # očekávání skladu:
    # B = alias (název z PDF)
    # D = aktuální stav
    # E = nový stav

    for i in range(len(sklad_df)):
        alias_raw = sklad_df.iloc[i, 1]  # sloupec B
        alias = normalizuj_alias(alias_raw)

        if alias == "" or alias.lower() == "nan":
            continue

        prodano_setu = 0

        if not df_povleceni.empty:
            combined = (
                df_povleceni["Typ produktu"].astype(str).apply(normalizuj_text)
                + " - "
                + df_povleceni["Název"].astype(str).apply(normalizuj_text)
            )

            match = df_povleceni[combined.str.contains(alias, case=False, na=False, regex=False)]

            if not match.empty:
                # 🔥 KLÍČ: sečteme všechny výskyty produktu v PDF
                prodano_setu = int(match["SETY"].sum())

        # aktuální stav
        aktualni = sklad_df.iloc[i, 3]  # sloupec D
        try:
            aktualni = int(aktualni)
        except:
            aktualni = 0

        # nový stav = odečteme sety
        sklad_df.iloc[i, 4] = aktualni - prodano_setu  # sloupec E

    soubor_sklad = vystup_slozka / "stav_skladu_po_odectu.xlsx"
    sklad_df.to_excel(soubor_sklad, index=False, engine="openpyxl")

    return {
        "povleceni": soubor_povleceni,
        "ostatni": soubor_ostatni,
        "sklad": soubor_sklad
    }






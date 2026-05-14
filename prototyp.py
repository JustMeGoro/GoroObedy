import os
import sqlite3
import requests
from bs4 import BeautifulSoup
import subprocess
import json
import difflib
import time

# ============= 1) AI ROZKLAD JÍDLA NA INGREDIENCE (DIAGNOSTIKA) =============

def ai_rozklad(jidlo: str) -> list:
    print("\n================ AI ROZKLAD ================")
    print("Jídlo:", jidlo)

    prompt = f"""
    Rozlož následující jídlo na seznam ingrediencí.
    Piš pouze seznam ingrediencí, žádné množství.

    Výstup MUSÍ být v jednom z těchto formátů:
    1) čistý JSON seznam: ["a","b","c"]
    2) seznam s pomlčkami:
       - a
       - b
       - c
    3) seznam oddělený čárkami: a, b, c

    Jídlo: {jidlo}
    """

    result = subprocess.run(
        ["ollama", "run", "mistral"],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE
    )

    text = result.stdout.decode("utf-8").strip()

    print("\n--- AI RAW OUTPUT ---")
    print(text)
    print("----------------------\n")

    # 1) JSON
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        json_text = text[start:end]
        data = json.loads(json_text)
        print("JSON detekován:", data)
        return data
    except Exception as e:
        print("JSON nenalezen:", e)

    # 2) Pomlčky
    lines = text.splitlines()
    pomlcky = [l.replace("-", "").strip() for l in lines if l.strip().startswith("-")]
    if pomlcky:
        print("Pomlčkový seznam detekován:", pomlcky)
        return pomlcky

    # 3) Čárky
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) > 1:
            print("Čárkový seznam detekován:", parts)
            return parts

    # 4) Fallback
    fallback = []
    for l in lines:
        if 1 <= len(l.split()) <= 3:
            fallback.append(l.strip())

    print("Fallback seznam:", fallback)
    return fallback


# ============= 2) FUZZY MATCH =============

def fuzzy_match(dotaz: str, moznosti: list) -> str | None:
    if not moznosti:
        return None
    match = difflib.get_close_matches(dotaz.lower(), [m.lower() for m in moznosti], n=1, cutoff=0.3)
    if match:
        for m in moznosti:
            if m.lower() == match[0]:
                return m
    return None


# ============= 3) HLEDÁNÍ V KALORICKE TABULKY.CZ (DIAGNOSTIKA) =============

BASE_KT = "https://www.kaloricketabulky.cz"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "cs-CZ,cs;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/"
}

def najdi_nejlepsi_shodu(dotaz: str) -> dict | None:
    print("\n>>> Hledám v KT:", dotaz)

    url = f"{BASE_KT}/hledani?q={dotaz}"
    r = requests.get(url, headers=HEADERS)

    print("HTTP status:", r.status_code)

    if r.status_code != 200:
        print("KT vrátily chybu, zkusíme ještě jednou s jiným UA...")
        r = requests.get(url, headers={
            **HEADERS,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
        })
        print("Druhý pokus status:", r.status_code)

    soup = BeautifulSoup(r.text, "html.parser")
    vysledky = soup.find_all("a", class_="search-result-item")

    print("Nalezeno výsledků:", len(vysledky))

    if not vysledky:
        return None

    nazvy = [v.get_text(strip=True) for v in vysledky]
    print("Názvy:", nazvy)

    nej = fuzzy_match(dotaz, nazvy)
    print("Fuzzy match:", nej)

    if not nej:
        return None

    for v in vysledky:
        if v.get_text(strip=True) == nej:
            url = BASE_KT + v["href"]
            print("Vybraná URL:", url)
            return {
                "ingredience": dotaz,
                "nalezeno": nej,
                "url": url
            }

    return None



# ============= 4) STAŽENÍ NUTRIČNÍCH HODNOT (DIAGNOSTIKA) =============

def stahni_nutricni_hodnoty(url: str) -> dict:
    print("\n>>> Stahuji nutriční hodnoty z:", url)

    r = requests.get(url)
    if r.status_code != 200:
        print("Chyba HTTP:", r.status_code)
        return {"kcal": None, "bilkoviny": None, "sacharidy": None, "tuky": None}

    soup = BeautifulSoup(r.text, "html.parser")

    kcal = None
    bilk = None
    sach = None
    tuky = None

    rows = soup.find_all("tr")
    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 2:
            continue

        label = tds[0].get_text(strip=True).lower()
        value = tds[1].get_text(strip=True).replace(",", ".").split()[0]

        try:
            num = float(value)
        except ValueError:
            continue

        if "energie" in label or "kcal" in label:
            kcal = int(num)
        elif "bílkovin" in label:
            bilk = num
        elif "sacharid" in label:
            sach = num
        elif "tuk" in label:
            tuky = num

    print("Nutriční hodnoty:", kcal, bilk, sach, tuky)

    return {
        "kcal": kcal,
        "bilkoviny": bilk,
        "sacharidy": sach,
        "tuky": tuky
    }


# ============= 5) ODHAD GRAMÁŽE =============

def odhad_gramaze(ingredience: str) -> int:
    ing = ingredience.lower()

    if "maso" in ing or "kuřecí" in ing or "hovězí" in ing or "vepř" in ing:
        return 150
    if "těstovin" in ing or "špaget" in ing:
        return 350
    if "rýž" in ing:
        return 180
    if "brambor" in ing:
        return 200
    if "sýr" in ing:
        return 30
    if "omáčk" in ing:
        return 80
    if "zelenin" in ing or "salát" in ing:
        return 100
    if "polév" in ing:
        return 300

    return 100


# ============= 6) STAŽENÍ JÍDELNÍČKU =============

def stahni_jidelnicek() -> list:
    URL = "https://secure.ulrichsw.cz/estrava/stara/jidelnicek2.php?idzar=103&lang=CZ"
    response = requests.get(URL)
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    tabulka = soup.find("table", class_="tabulka_1")
    if not tabulka:
        return []

    rows = tabulka.find_all("tr")
    vysledky = []

    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        if cells[0].get("class") == ["bunka_1"]:
            continue

        if len(cells) < 2:
            continue

        datum = cells[0].get_text(" ", strip=True)

        vnitrni = cells[1].find("table")
        if not vnitrni:
            continue

        jidla = vnitrni.find_all("tr")

        polevka = jidla[0].get_text(" ", strip=True) if len(jidla) > 0 else ""
        obed1 = jidla[1].get_text(" ", strip=True) if len(jidla) > 1 else ""
        obed2 = ""

        if len(jidla) > 2:
            text3 = jidla[2].get_text(" ", strip=True)
            if "Oběd 2" in text3 or "2" in text3:
                obed2 = text3

        vysledky.append({
            "datum": datum,
            "polevka": polevka,
            "obed1": obed1,
            "obed2": obed2
        })

    return vysledky


# ============= 7) DATABÁZE =============

DB_PATH = "database/obedy.db"

def init_db():
    if not os.path.exists("database"):
        os.makedirs("database")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS obedy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datum TEXT,
            nazev TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ingredience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            obed_id INTEGER,
            nazev TEXT,
            nalezeno TEXT,
            url TEXT,
            gramaz INTEGER,
            kcal INTEGER,
            bilkoviny REAL,
            sacharidy REAL,
            tuky REAL,
            FOREIGN KEY(obed_id) REFERENCES obedy(id)
        )
    """)

    conn.commit()
    conn.close()


def uloz_obed(datum: str, nazev: str, ingredience_list: list):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("INSERT INTO obedy (datum, nazev) VALUES (?, ?)", (datum, nazev))
    obed_id = c.lastrowid

    for ing in ingredience_list:
        c.execute("""
            INSERT INTO ingredience
            (obed_id, nazev, nalezeno, url, gramaz, kcal, bilkoviny, sacharidy, tuky)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            obed_id,
            ing["ingredience"],
            ing["nalezeno"],
            ing["url"],
            ing["gramaz"],
            ing.get("kcal"),
            ing.get("bilkoviny"),
            ing.get("sacharidy"),
            ing.get("tuky"),
        ))

    conn.commit()
    conn.close()


# ============= 8) HLAVNÍ LOGIKA =============

def zpracuj_jidlo(nazev_jidla: str) -> list:
    ingredience = ai_rozklad(nazev_jidla)
    print(">>> AI ingredience:", ingredience)

    vysledky = []

    for ing in ingredience:
        nalezene = najdi_nejlepsi_shodu(ing)
        print(">>> Výsledek hledání:", nalezene)

        if not nalezene:
            continue

        gramaz = odhad_gramaze(ing)
        nutri = stahni_nutricni_hodnoty(nalezene["url"])

        nalezene["gramaz"] = gramaz
        nalezene["kcal"] = nutri["kcal"]
        nalezene["bilkoviny"] = nutri["bilkoviny"]
        nalezene["sacharidy"] = nutri["sacharidy"]
        nalezene["tuky"] = nutri["tuky"]

        vysledky.append(nalezene)

        time.sleep(0.7)

    print(">>> Finální ingredience:", vysledky)
    return vysledky


def main():
    init_db()
    jidelnicek = stahni_jidelnicek()

    for den in jidelnicek:
        if not den["obed1"]:
            continue

        print(f"\n================ ZPRACOVÁVÁM: {den['datum']} – {den['obed1']} ================")

        ingredience_list = zpracuj_jidlo(den["obed1"])

        print(f"  → nalezeno ingrediencí: {len(ingredience_list)}")

        uloz_obed(den["datum"], den["obed1"], ingredience_list)

    print("\nHotovo! Obědy byly uloženy do database/obedy.db")


if __name__ == "__main__":
    main()

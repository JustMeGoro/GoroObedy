import os
import sqlite3
import requests
from bs4 import BeautifulSoup

# ============= 1) STAŽENÍ JÍDELNÍČKU =============

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
            polevka TEXT,
            obed1 TEXT,
            obed2 TEXT
        )
    """)

    c.execute("PRAGMA table_info(obedy)")
    existing_columns = [row[1] for row in c.fetchall()]

    if "polevka" not in existing_columns:
        c.execute("ALTER TABLE obedy ADD COLUMN polevka TEXT")
    if "obed1" not in existing_columns:
        c.execute("ALTER TABLE obedy ADD COLUMN obed1 TEXT")
    if "obed2" not in existing_columns:
        c.execute("ALTER TABLE obedy ADD COLUMN obed2 TEXT")

    conn.commit()
    conn.close()


def uloz_obed(datum: str, polevka: str, obed1: str, obed2: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "INSERT INTO obedy (datum, polevka, obed1, obed2) VALUES (?, ?, ?, ?)",
        (datum, polevka, obed1, obed2)
    )

    conn.commit()
    conn.close()


# ============= 8) HLAVNÍ LOGIKA =============

def main():
    init_db()
    jidelnicek = stahni_jidelnicek()

    for den in jidelnicek:
        if not den["obed1"] and not den["obed2"] and not den["polevka"]:
            continue

        print(f"\n================ ZPRACOVÁVÁM: {den['datum']} ================")
        print("  Polevka:", den["polevka"])
        print("  Oběd 1:", den["obed1"])
        print("  Oběd 2:", den["obed2"])

        uloz_obed(den["datum"], den["polevka"], den["obed1"], den["obed2"])

    print("\nHotovo! Obědy byly uloženy do database/obedy.db")


if __name__ == "__main__":
    main()

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import csv
import psycopg2
from datetime import date
import time
import os
from dotenv import load_dotenv

load_dotenv()
db_password = os.getenv("DB_PASSWORD")

URL = "https://www.resmigazete.gov.tr/eskiler/2026/06/20260603.htm"
GAZETTE_DATE = date(2026, 6, 3)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

response = requests.get(URL, headers=headers, timeout=15)
response.encoding = response.apparent_encoding

print("Status code:", response.status_code)

soup = BeautifulSoup(response.text, "html.parser")

rows = []
bolum = ""

for p in soup.find_all("p"):
    a = p.find("a")
    if a:
        text = re.sub(r"\s+", " ", a.get_text(strip=True)).strip().lstrip("– —-")
        href = a.get("href")
        if text and href:
            rows.append({"title": text, "link": urljoin(URL, href), "bolum": bolum})
    else:
        baslik_metni = re.sub(r"\s+", " ", p.get_text(strip=True)).strip()
        if "BÖLÜMÜ" in baslik_metni.upper():
            bolum = baslik_metni

print(f"{len(rows)} link bulundu.")

with open("resmi_gazete_test.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "link", "bolum"])
    writer.writeheader()
    writer.writerows(rows)

print("CSV yazildi: resmi_gazete_test.csv")

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="gazette_db",
    user="postgres",
    password=db_password,
)
cur = conn.cursor()

cur.execute(
    "INSERT INTO gazette_issue (date, url) VALUES (%s, %s) RETURNING id",
    (GAZETTE_DATE, URL),
)
gazette_id = cur.fetchone()[0]
print("gazette_issue id:", gazette_id)

TABLO_ESLESME = {
    "YASAMA": "legislative_section",
    "YÜRÜTME": "executive_administrative_section",
    "YARGI": "judicial_section",
    "İLAN": "announcement_section",
}

def normalize_bolum(metin):
    degisim = {"Â": "A", "â": "a", "Î": "I", "î": "i", "Û": "U", "û": "u"}
    for eski, yeni in degisim.items():
        metin = metin.replace(eski, yeni)
    return metin

eklenen = 0
for row in rows:
    b = normalize_bolum(row["bolum"]).upper()
    tablo = None
    for anahtar, tablo_adi in TABLO_ESLESME.items():
        if anahtar in b:
            tablo = tablo_adi
            break
    if tablo is None:
        continue

    icerik_bytes = None
    try:
        icerik_response = requests.get(row["link"], headers=headers, timeout=15)
        icerik_response.raise_for_status()
        icerik_bytes = icerik_response.content
    except requests.RequestException as e:
        print(f"Icerik cekilemedi ({row['link']}): {e}")

    cur.execute(
        f"INSERT INTO {tablo} (gazette_id, title, link, pdf_content) VALUES (%s, %s, %s, %s)",
        (
            gazette_id,
            row["title"],
            row["link"],
            psycopg2.Binary(icerik_bytes) if icerik_bytes is not None else None,
        ),
    )
    eklenen += 1

    time.sleep(0.5)

conn.commit()
print(f"{eklenen} satir veritabanina yazildi.")

cur.close()
conn.close()
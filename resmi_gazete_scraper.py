import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import psycopg2
from datetime import date
import time
import os
from dotenv import load_dotenv
import fitz
import pytesseract
from PIL import Image
import io

load_dotenv()
db_password = os.getenv("DB_PASSWORD")

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tessdata")
TESSERACT_CONFIG = f"--tessdata-dir {TESSDATA_DIR}"


def pdf_to_text_via_ocr(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    sayfa_metinleri = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        sayfa_metinleri.append(pytesseract.image_to_string(img, lang="tur", config=TESSERACT_CONFIG))
    doc.close()
    return "\n".join(sayfa_metinleri)

URL = "https://www.resmigazete.gov.tr/eskiler/2026/06/20260603.htm"
GAZETTE_DATE = date(2026, 6, 3)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

response = requests.get(URL, headers=headers, timeout=15)
response.raise_for_status()
response.encoding = response.apparent_encoding

print("Status code:", response.status_code)

soup = BeautifulSoup(response.text, "html.parser")

issue_number = None
m = re.search(r"(\d+)\s*Sayılı", response.text)
if m:
    issue_number = int(m.group(1))

whole_issue_pdf_url = URL.rsplit(".htm", 1)[0] + ".pdf"
whole_issue_pdf_content = None
try:
    pdf_response = requests.get(whole_issue_pdf_url, headers=headers, timeout=15)
    pdf_response.raise_for_status()
    whole_issue_pdf_content = pdf_response.content
except requests.RequestException as e:
    print(f"Gazete PDF'i cekilemedi ({whole_issue_pdf_url}): {e}")

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

def temizle_null_bayt(metin):
    return metin.replace("\x00", "")

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="gazette_db",
    user="postgres",
    password=db_password,
)
try:
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO gazette_issue (date, url, issue_number, pdf_url, pdf_content) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (
            GAZETTE_DATE,
            URL,
            issue_number,
            whole_issue_pdf_url,
            psycopg2.Binary(whole_issue_pdf_content) if whole_issue_pdf_content is not None else None,
        ),
    )
    gazette_id = cur.fetchone()[0]
    print("gazette_issue id:", gazette_id)

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
        content_type = None
        try:
            icerik_response = requests.get(row["link"], headers=headers, timeout=15)
            icerik_response.raise_for_status()
            
            if row["link"].lower().endswith(".pdf"):
                # PDF'i indirip OCR ile metne çeviriyoruz
                metin = temizle_null_bayt(pdf_to_text_via_ocr(icerik_response.content))
                icerik_bytes = metin.encode("utf-8")
                content_type = "pdf_ocr"
            else:
                icerik_response.encoding = icerik_response.apparent_encoding
                icerik_soup = BeautifulSoup(icerik_response.text, "html.parser")
                metin = temizle_null_bayt(icerik_soup.get_text(separator="\n", strip=True))
                icerik_bytes = metin.encode("utf-8")
                content_type = "html_text"
                
        except Exception as e:
            print(f"Icerik cekilemedi veya islenemedi ({row['link']}): {e}")
            continue  # Hatalı maddeyi atla, tüm günü çökertme!

        cur.execute(
            f"INSERT INTO {tablo} (gazette_id, title, link, pdf_content, content_type) "
            f"VALUES (%s, %s, %s, %s, %s)",
            (
                gazette_id,
                temizle_null_bayt(row["title"]),
                temizle_null_bayt(row["link"]),
                psycopg2.Binary(icerik_bytes) if icerik_bytes is not None else None,
                content_type,
            ),
        )
        eklenen += 1
        time.sleep(0.5)

    conn.commit()
    print(f"{eklenen} satir veritabanina yazildi.")
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
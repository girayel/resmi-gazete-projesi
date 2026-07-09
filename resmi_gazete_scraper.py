import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import psycopg2
from datetime import date, timedelta
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

# Test icin 1 haftalik araligi kullaniyoruz. Tam yila gecmek icin:
# BASLANGIC_TARIHI = date(2025, bugunun ayı, gunu)
# BITIS_TARIHI = date.today()
BASLANGIC_TARIHI = date(2026, 6, 1)
BITIS_TARIHI = date(2026, 6, 7)

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

TABLO_ESLESME = {
    "YASAMA": "legislative_section",
    "YÜRÜTME": "executive_administrative_section",
    "YARGI": "judicial_section",
    "İLAN": "announcement_section",
}


def pdf_to_text_via_ocr(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    sayfa_metinleri = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        sayfa_metinleri.append(pytesseract.image_to_string(img, lang="tur", config=TESSERACT_CONFIG))
    doc.close()
    return "\n".join(sayfa_metinleri)


def normalize_bolum(metin):
    degisim = {"Â": "A", "â": "a", "Î": "I", "î": "i", "Û": "U", "û": "u"}
    for eski, yeni in degisim.items():
        metin = metin.replace(eski, yeni)
    return metin


def temizle_null_bayt(metin):
    return metin.replace("\x00", "")


def gunluk_url_olustur(gun):
    return f"https://www.resmigazete.gov.tr/eskiler/{gun.year}/{gun.month:02d}/{gun.year}{gun.month:02d}{gun.day:02d}.htm"


def gazette_id_var_mi(cur, gun):
    cur.execute("SELECT id FROM gazette_issue WHERE date = %s", (gun,))
    sonuc = cur.fetchone()
    return sonuc[0] if sonuc else None


def madde_listesini_cikar(soup, url):
    rows = []
    bolum = ""
    for p in soup.find_all("p"):
        a = p.find("a")
        if a:
            text = re.sub(r"\s+", " ", a.get_text(strip=True)).strip().lstrip("– —-")
            href = a.get("href")
            if text and href:
                rows.append({"title": text, "link": urljoin(url, href), "bolum": bolum})
        else:
            baslik_metni = re.sub(r"\s+", " ", p.get_text(strip=True)).strip()
            if "BÖLÜMÜ" in baslik_metni.upper():
                bolum = baslik_metni
    return rows


def madde_icerigini_getir(link):
    icerik_response = requests.get(link, headers=headers, timeout=15)
    icerik_response.raise_for_status()

    if link.lower().endswith(".pdf"):
        metin = temizle_null_bayt(pdf_to_text_via_ocr(icerik_response.content))
        content_type = "pdf_ocr"
    else:
        icerik_response.encoding = icerik_response.apparent_encoding
        icerik_soup = BeautifulSoup(icerik_response.text, "html.parser")
        metin = temizle_null_bayt(icerik_soup.get_text(separator="\n", strip=True))
        content_type = "html_text"

    return metin.encode("utf-8"), content_type


def gunu_isle(cur, gun):
    if gazette_id_var_mi(cur, gun) is not None:
        print(f"{gun}: zaten kayitli, atlaniyor.")
        return 0

    url = gunluk_url_olustur(gun)
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"{gun}: sayfa bulunamadi/cekilemedi, atlaniyor. ({e})")
        return 0

    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    issue_number = None
    m = re.search(r"(\d+)\s*Sayılı", response.text)
    if m:
        issue_number = int(m.group(1))

    whole_issue_pdf_url = url.rsplit(".htm", 1)[0] + ".pdf"
    whole_issue_pdf_content = None
    try:
        pdf_response = requests.get(whole_issue_pdf_url, headers=headers, timeout=15)
        pdf_response.raise_for_status()
        whole_issue_pdf_content = pdf_response.content
    except requests.RequestException as e:
        print(f"{gun}: gazete PDF'i cekilemedi ({whole_issue_pdf_url}): {e}")

    rows = madde_listesini_cikar(soup, url)
    print(f"{gun}: {len(rows)} link bulundu.")

    cur.execute(
        "INSERT INTO gazette_issue (date, url, issue_number, pdf_url, pdf_content) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (
            gun,
            url,
            issue_number,
            whole_issue_pdf_url,
            psycopg2.Binary(whole_issue_pdf_content) if whole_issue_pdf_content is not None else None,
        ),
    )
    gazette_id = cur.fetchone()[0]

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

        try:
            icerik_bytes, content_type = madde_icerigini_getir(row["link"])
        except Exception as e:
            print(f"Icerik cekilemedi veya islenemedi ({row['link']}): {e}")
            continue

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

    print(f"{gun}: {eklenen} satir veritabanina yazildi.")
    return eklenen


conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="gazette_db",
    user="postgres",
    password=db_password,
)
try:
    cur = conn.cursor()

    toplam_gun = 0
    toplam_madde = 0
    gun = BASLANGIC_TARIHI
    while gun <= BITIS_TARIHI:
        try:
            eklenen = gunu_isle(cur, gun)
            conn.commit()
            if eklenen:
                toplam_gun += 1
                toplam_madde += eklenen
        except Exception as e:
            conn.rollback()
            print(f"{gun}: gun islenirken hata olustu, atlaniyor. ({e})")
        gun += timedelta(days=1)

    print(f"Bitti: {toplam_gun} gun, {toplam_madde} madde veritabanina yazildi.")
finally:
    conn.close()
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import psycopg2
from datetime import date, timedelta
import time
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import fitz
import pytesseract
from PIL import Image
import io
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()
db_password = os.getenv("DB_PASSWORD")

# SMTP ayari yoksa (SMTP_HOST bos) bildirimler gercekten gonderilmez, sadece
# konsola [SIMULASYON] olarak yazilir - eslesme/tekrar-gondermeme mantigini
# gercek bir e-posta sunucusu olmadan da test edebilmek icin.
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tessdata")
TESSERACT_CONFIG = f"--tessdata-dir {TESSDATA_DIR}"

# Test icin 1 haftalik araligi kullaniyoruz. Tam yila gecmek icin:
# BASLANGIC_TARIHI = date(2025, bugun.month, bugun.day)
# BITIS_TARIHI = date.today()
BASLANGIC_TARIHI = date(2025, 6, 7)
BITIS_TARIHI = date.today()

# ========== JOB: AYARLAR ==========
BATCH_BOYUTU = 5
BATCH_ARASI_BEKLEME_SN = 5
BOS_KUYRUK_BEKLEME_SN = 300

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


# ========== JOB: HATA LOGLAMA ==========
def error_log_tablosunu_olustur(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS error_log (
            id serial PRIMARY KEY,
            gazette_date date,
            gazette_id integer,
            link varchar,
            seviye varchar(10),
            hata_mesaji text,
            olusturma_zamani timestamptz DEFAULT now()
        )
        """
    )


def error_log_yaz(cur, gun, gazette_id, link, seviye, mesaj):
    cur.execute(
        "INSERT INTO error_log (gazette_date, gazette_id, link, seviye, hata_mesaji) "
        "VALUES (%s, %s, %s, %s, %s)",
        (gun, gazette_id, link, seviye, mesaj),
    )


# ========== JOB: KUYRUK ==========
def bekleyen_gunleri_getir(cur, baslangic, bitis, adet):
    cur.execute(
        "SELECT date FROM gazette_issue WHERE date BETWEEN %s AND %s "
        "UNION "
        "SELECT gazette_date FROM error_log WHERE seviye = 'gun' AND gazette_date BETWEEN %s AND %s",
        (baslangic, bitis, baslangic, bitis),
    )
    islenmis = {row[0] for row in cur.fetchall()}

    bekleyenler = []
    gun = baslangic
    while gun <= bitis and len(bekleyenler) < adet:
        if gun not in islenmis:
            bekleyenler.append(gun)
        gun += timedelta(days=1)
    return bekleyenler


# ========== JOB: KEYWORD ESLESTIRME ==========
def takip_edilen_kelimeleri_getir(cur):
    """Havuzdaki her keyword'u, onu takip eden kullanicilarla birlikte dondurur.
    {keyword: [(user_id, email), ...]} seklinde. Batch basina bir kez cagrilir;
    her madde icin ayri sorgu atmamak icin sonuc bellekte tutulur."""
    cur.execute(
        "SELECT k.keyword, u.id, u.email "
        "FROM user_keywords uk "
        "JOIN keywords k ON k.id = uk.keyword_id "
        "JOIN users u ON u.id = uk.user_id"
    )
    takip = {}
    for keyword, user_id, email in cur.fetchall():
        takip.setdefault(keyword, []).append((user_id, email))
    return takip


def kelime_desenleri_olustur(takip_edilen_kelimeler):
    """Her keyword icin, metinde bir kelimenin BASLANGICI olarak gecip gecmedigini
    kontrol eden bir regex derler. Sadece sol tarafta \b (kelime siniri) araniyor;
    sag tarafta aranmiyor cunku Turkce eklemeli bir dil - 'kanun' koku metinde
    neredeyse hep 'kanunun', 'kanuna', 'kanunla' gibi ek almis halde gecer, bunlari
    kacirmamak icin sag sinir zorunlu tutulmuyor. Sol sinir sayesinde 'muhtac',
    'taraf' gibi kelimenin ORTASINDA rastgele gecen harf dizileri hala eslesmez."""
    return {
        keyword: re.compile(r"\b" + re.escape(keyword), re.IGNORECASE)
        for keyword in takip_edilen_kelimeler
    }


def metinde_eslesen_kelimeleri_bul(metin, takip_edilen_kelimeler, kelime_desenleri):
    """Verilen metin icinde, takip edilen keyword'lerden hangilerinin bagimsiz
    bir kelime olarak gectigini bulur. {keyword: [(user_id, email), ...]} dondurur."""
    eslesmeler = {}
    for keyword, takipciler in takip_edilen_kelimeler.items():
        if kelime_desenleri[keyword].search(metin):
            eslesmeler[keyword] = takipciler
    return eslesmeler


# ========== JOB: BILDIRIM ==========
def notification_log_tablosunu_olustur(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_log (
            id serial PRIMARY KEY,
            user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            madde_tablosu varchar(50) NOT NULL,
            madde_id integer NOT NULL,
            eslesen_kelimeler text NOT NULL,
            gonderim_zamani timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, madde_tablosu, madde_id)
        )
        """
    )


def bildirim_kayit_olustur(cur, user_id, madde_tablosu, madde_id, kelimeler):
    """notification_log'a kayit eklemeyi dener. Bu kullanici+madde icin daha once
    kayit varsa (UNIQUE kisitlamasi) hicbir sey yapmaz. Yeni bir kayit olusturulduysa
    True, zaten varsa (tekrar bildirim gonderilmemeli) False dondurur."""
    cur.execute(
        "INSERT INTO notification_log (user_id, madde_tablosu, madde_id, eslesen_kelimeler) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (user_id, madde_tablosu, madde_id) DO NOTHING "
        "RETURNING id",
        (user_id, madde_tablosu, madde_id, ", ".join(sorted(kelimeler))),
    )
    return cur.fetchone() is not None


def bildirim_epostasi_gonder(hedef_email, konu, govde):
    if not SMTP_HOST:
        print(f"  [SIMULASYON] SMTP yapilandirilmamis, gercek eposta gonderilmedi -> {hedef_email}: {konu}")
        return

    try:
        mesaj = EmailMessage()
        mesaj["Subject"] = konu
        mesaj["From"] = SMTP_FROM
        mesaj["To"] = hedef_email
        mesaj.set_content(govde)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as sunucu:
            sunucu.starttls()
            sunucu.login(SMTP_USER, SMTP_PASSWORD)
            sunucu.send_message(mesaj)
        print(f"  [EPOSTA] Gonderildi -> {hedef_email}: {konu}")
    except Exception as e:
        print(f"  [EPOSTA HATASI] {hedef_email}: {e}")


def eslesmeleri_gunluk_ozete_ekle(gunluk_bildirimler, eslesmeler, madde_tablosu, madde_id, baslik, link):
    """Bir maddenin eslesmelerini hemen mail atmak yerine, gunun sonunda tek ozet
    olarak gondermek uzere biriktirir."""
    kullanici_bazinda = {}
    for keyword, takipciler in eslesmeler.items():
        for user_id, email in takipciler:
            kullanici_bazinda.setdefault(user_id, {"email": email, "kelimeler": []})
            kullanici_bazinda[user_id]["kelimeler"].append(keyword)

    for user_id, bilgi in kullanici_bazinda.items():
        gunluk_bildirimler.setdefault(user_id, {"email": bilgi["email"], "maddeler": []})
        gunluk_bildirimler[user_id]["maddeler"].append({
            "tablo": madde_tablosu,
            "id": madde_id,
            "baslik": baslik,
            "link": link,
            "kelimeler": bilgi["kelimeler"],
        })


def gunluk_ozet_bildirimlerini_gonder(cur, gunluk_bildirimler):
    """Bir gunluk gazete islendikten sonra cagrilir; her kullaniciya, o gun icin
    (daha once bildirilmemis) tum eslesen maddeleri TEK bir ozet mailde toplar."""
    for user_id, bilgi in gunluk_bildirimler.items():
        yeni_maddeler = []
        for madde in bilgi["maddeler"]:
            yeni_mi = bildirim_kayit_olustur(cur, user_id, madde["tablo"], madde["id"], madde["kelimeler"])
            if yeni_mi:
                yeni_maddeler.append(madde)

        if not yeni_maddeler:
            continue

        konu = f"Resmi Gazete Gunluk Ozet: {len(yeni_maddeler)} yeni eslesme"
        satirlar = [
            f"- {madde['baslik']}\n  {madde['link']}\n  Eslesen kelimeler: {', '.join(madde['kelimeler'])}"
            for madde in yeni_maddeler
        ]
        govde = (
            f"Takip ettiginiz kelimelerle eslesen {len(yeni_maddeler)} yeni Resmi Gazete maddesi var:\n\n"
            + "\n\n".join(satirlar)
        )
        bildirim_epostasi_gonder(bilgi["email"], konu, govde)


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


def gunu_isle(cur, gun, takip_edilen_kelimeler, kelime_desenleri):
    url = gunluk_url_olustur(gun)
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        # Gecici bir baglanti/DNS sorunu olabilir (ornegin internetin anlik kesilmesi).
        # "gun" seviyesinde loglamiyoruz ki bekleyen_gunleri_getir bu gunu kuyruktan
        # dusurmesin - bir sonraki batch'te tekrar denensin.
        print(f"{gun}: baglanti hatasi, sonraki calistirmada tekrar denenecek. ({e})")
        error_log_yaz(cur, gun, None, url, "baglanti", str(e))
        return 0
    except requests.RequestException as e:
        print(f"{gun}: sayfa bulunamadi/cekilemedi, atlaniyor. ({e})")
        error_log_yaz(cur, gun, None, url, "gun", str(e))
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
        error_log_yaz(cur, gun, None, whole_issue_pdf_url, "gun", str(e))

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
    gunluk_bildirimler = {}
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
            error_log_yaz(cur, gun, gazette_id, row["link"], "madde", str(e))
            continue

        cur.execute(
            f"INSERT INTO {tablo} (gazette_id, title, link, pdf_content, content_type) "
            f"VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (
                gazette_id,
                temizle_null_bayt(row["title"]),
                temizle_null_bayt(row["link"]),
                psycopg2.Binary(icerik_bytes) if icerik_bytes is not None else None,
                content_type,
            ),
        )
        madde_id = cur.fetchone()[0]
        eklenen += 1

        icerik_metni = icerik_bytes.decode("utf-8", errors="ignore") if icerik_bytes else ""
        eslesmeler = metinde_eslesen_kelimeleri_bul(row["title"] + " " + icerik_metni, takip_edilen_kelimeler, kelime_desenleri)
        if eslesmeler:
            eslesmeleri_gunluk_ozete_ekle(gunluk_bildirimler, eslesmeler, tablo, madde_id, row["title"], row["link"])

        time.sleep(0.2)

    gunluk_ozet_bildirimlerini_gonder(cur, gunluk_bildirimler)
    print(f"{gun}: {eklenen} satir veritabanina yazildi.")
    return eklenen


# ========== JOB: ANA DONGU ==========
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="gazette_db",
    user="postgres",
    password=db_password,
)
try:
    cur = conn.cursor()
    error_log_tablosunu_olustur(cur)
    notification_log_tablosunu_olustur(cur)
    conn.commit()

    print(f"Job baslatildi: {BASLANGIC_TARIHI} - {BITIS_TARIHI} araligi taranacak.")
    while True:
        bekleyenler = bekleyen_gunleri_getir(cur, BASLANGIC_TARIHI, BITIS_TARIHI, BATCH_BOYUTU)

        if not bekleyenler:
            print(f"Islenecek gun kalmadi. {BOS_KUYRUK_BEKLEME_SN} saniye sonra tekrar kontrol edilecek.")
            time.sleep(BOS_KUYRUK_BEKLEME_SN)
            continue

        takip_edilen_kelimeler = takip_edilen_kelimeleri_getir(cur)
        kelime_desenleri = kelime_desenleri_olustur(takip_edilen_kelimeler)
        print(f"Yeni batch: {len(bekleyenler)} gun islenecek ({bekleyenler[0]} - {bekleyenler[-1]}), "
              f"{len(takip_edilen_kelimeler)} kelime takip ediliyor.")
        for gun in bekleyenler:
            try:
                gunu_isle(cur, gun, takip_edilen_kelimeler, kelime_desenleri)
                conn.commit()
            except Exception as e:
                conn.rollback()
                error_log_yaz(cur, gun, None, None, "gun", str(e))
                conn.commit()
                print(f"{gun}: gun islenirken beklenmeyen hata, error_log'a yazildi. ({e})")

        print(f"Batch bitti. {BATCH_ARASI_BEKLEME_SN} saniye bekleniyor.")
        time.sleep(BATCH_ARASI_BEKLEME_SN)
finally:
    conn.close()

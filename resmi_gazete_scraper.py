import re                         # bulunan metinlerdeki fazla bosluk/satir basi gibi kirliligi temizlemek (regex ile) icin
import requests                    # web sayfasini indirmek (HTTP GET istegi atmak) icin
from bs4 import BeautifulSoup      # indirilen ham HTML'i parse edip icinde <a> gibi
                                    # etiketleri kolayca arayabilmek icin
from urllib.parse import urljoin   # sayfadaki linkler bazen goreceli olur (orn. "/eskiler/2026/06/x.htm");
                                    # urljoin bunu ana URL ile birlestirip tam/tiklanabilir link yapar
import csv                         # Python'in kendi built-in CSV yazma modulu, ekstra kurulum istemez
import psycopg2                    # PostgreSQL'e Python'dan baglanmayi saglayan kutuphane
from datetime import date          # gazette_issue tablosuna yazacagimiz tarihi olusturmak icin
import time                        # her link icin ayri istek atarken aralara kisa bekleme koymak icin
import os                          # .env icindeki sifreyi okuyabilmek icin
from dotenv import load_dotenv     # .env dosyasindaki degiskenleri yuklemek icin

load_dotenv()
db_password = os.getenv("DB_PASSWORD")

# URL formati: https://www.resmigazete.gov.tr/eskiler/YYYY/AA/YYYYAAGG.htm
# Neden sabit (hardcoded)? ilk adım -> statik bir link verip o gunu cekmek
# Ileride bu satir bir donguye girip her gun icin otomatik degisecek.
URL = "https://www.resmigazete.gov.tr/eskiler/2026/06/20260603.htm"
GAZETTE_DATE = date(2026, 6, 3)     # URL'deki tarihle ayni olmali

# Neden User-Agent header ekliyoruz?
# requests varsayilan olarak kendini "python-requests/x.x" diye tanitir, bazi siteler
# bunu gorunce bot sanip istegi reddedebilir. Gercek bir tarayici gibi gorununce
# (Chrome/Windows user-agent'i) daha az sorunla karsilasiriz.
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# requests.get: asil HTTP istegi burada atiliyor, sayfayi indiriyor
# timeout=15: sunucu 15 saniyede cevap vermezse sonsuza kadar takili kalmak yerine hata verip durur
response = requests.get(URL, headers=headers, timeout=15)

# Neden encoding'i elle ayarliyoruz?
# Turkce siteler bazen eski "windows-1254" kodlamasini kullanir, requests bunu yanlis
# tahmin edip c/s/g/i/o/u karakterlerini bozuk gosterebilir.
# apparent_encoding icerige bakip gercek kodlamayi tahmin etmeye calisir; yine de
# bozuk cikarsa bu satiri elle "windows-1254" yapman gerekebilir.
response.encoding = response.apparent_encoding

print("Status code:", response.status_code)  # 200 = basarili; 403/404/500 gibi bir sey gorursen sorun var demektir

# BeautifulSoup(response.text, "html.parser"): indirdigimiz ham HTML string'ini
# gezilebilir bir agac yapisina ceviriyor, boylece "sayfadaki tum <a> etiketlerini ver"
# gibi sorgular yapabiliyoruz. "html.parser" Python'in kendi parser'i, ekstra kurulum istemez.
soup = BeautifulSoup(response.text, "html.parser")

#  <a> yerine <p> etiketlerini geziyoruz.
# Neden? Gercek sayfaya bakinca goruldu ki sayfadaki her satir (hem "YASAMA BOLUMU" gibi
# bolum basliklari hem de her bir gazete maddesi) bir <p> etiketinin icinde duruyor.
# Bir <p>'nin icinde link varsa bu bir gazete maddesi demek; link yoksa ve metninde
# "BOLUMU" geciyorsa bu bir bolum basligi demek. Bu yuzden artik <p>'leri sirayla gezip
# hangisinin hangi tur oldugunu ayirt ediyoruz.
rows = []
bolum = ""   # su an hangi bolumun icinde oldugumuzu tutan degisken. Bas tarafta henuz
             # hicbir bolum basligina rastlanmadigi icin bos string ile basliyoruz.

for p in soup.find_all("p"):            # sayfadaki her <p> etiketini tek tek geziyoruz
    a = p.find("a")                     # bu <p>'nin icinde bir <a> (link) var mi diye bakiyoruz
                                         # not: bir <p> icinde birden fazla link olsa bile
                                         # sadece ilkini yakalar, simdilik yeterli varsayiyoruz
    if a:                                # varsa, bu bir gazete maddesi (link) satiri demektir
        text = re.sub(r"\s+", " ", a.get_text(strip=True)).strip().lstrip("– —-")
        # re.sub(r"\s+", " ", ...): HTML'den gelen metinde satir sonlari/coklu bosluklar
        # olabiliyor, hepsini tek bosluga indirgiyoruz (duzgun gorunmesi icin)
        # .lstrip("– —-"): gazete maddeleri genelde "– " ya da "— " gibi bir tire ile
        # basliyor (site ornegi: "–– ... Yonetmeligi"), bu tireyi bastan temizliyoruz
        href = a.get("href")
        if text and href:
            rows.append({"title": text, "link": urljoin(URL, href), "bolum": bolum})
            # o an hangi bolumdeysek (bolum degiskeninin o anki degeri) bu satiri
            # onunla etiketliyoruz, boylece hangi maddenin hangi bolume ait oldugunu
            # (yasama / yurutme ve idare / yargi / ilan) kaybetmeden CSV'ye tasiyoruz
    else:
        # link yoksa, bu satir bir bolum basligi OLABILIR (ya da alakasiz bir paragraf)
        baslik_metni = re.sub(r"\s+", " ", p.get_text(strip=True)).strip()
        if "BÖLÜMÜ" in baslik_metni.upper():
            # .upper(): buyuk/kucuk harf farkindan etkilenmemek icin karsilastirmadan
            # once metni tamamen buyuk harfe ceviriyoruz
            bolum = baslik_metni   # bundan sonraki linkler artik bu yeni bolume ait sayilacak

print(f"{len(rows)} link bulundu.")

# csv.DictWriter: her satiri sozluk (dict) olarak verip otomatik CSV formatina ceviren yardimci sinif
# newline="": Windows'ta CSV yazarken satirlar arasinda fazladan bos satir cikmasini engeller
# encoding="utf-8-sig": basina BOM ekler, Excel'de acinca Turkce karakterlerin dogru gorunmesini saglar
with open("resmi_gazete_test.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "link", "bolum"])
    writer.writeheader()
    writer.writerows(rows)

print("CSV yazildi: resmi_gazete_test.csv")

# ============================================
# VERITABANINA YAZMA
# ============================================

# DBeaver'da baglanirken kullandigin bilgilerin ayni: host, port, database, kullanici, sifre
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="gazette_db",
    user="postgres",
    password=db_password,   # .env dosyasindaki DB_PASSWORD'den okunuyor
)
cur = conn.cursor()

# 1) Once ana tabloya (gazette_issue) bu gunun kaydini atiyoruz.
# RETURNING id: INSERT ile birlikte otomatik olusan id'yi de geri istiyoruz,
# cunku bu id'yi asagida her maddeyle iliskilendirmemiz (gazette_id) lazim.
cur.execute(
    "INSERT INTO gazette_issue (date, url) VALUES (%s, %s) RETURNING id",
    (GAZETTE_DATE, URL),
)
gazette_id = cur.fetchone()[0]
print("gazette_issue id:", gazette_id)

# 2) bolum metnini hangi tabloya yazacagimizi soyleyen basit bir eslesme.
# Anahtar kelime ile kontrol ediyoruz (tam esitlik degil), cunku sitedeki
# gercek metin "YASAMA BÖLÜMÜ" gibi ekstra kelimeler icerebilir.
TABLO_ESLESME = {
    "YASAMA": "legislative_section",
    "YÜRÜTME": "executive_administrative_section",
    "YARGI": "judicial_section",
    "İLAN": "announcement_section",
}

# YENI: bazi resmi metinlerde kelimeler sapka (^) isaretli harflerle yazilir
# (site ornegi: "İLÂN BÖLÜMÜ" - duz "İLAN" degil). Bu sapkali harfleri (Â, Î, Û)
# duz karsiliklarina cevirmezsek, yukaridaki TABLO_ESLESME ile karsilastirma
# tutmuyor ve o satirlar sessizce atlaniyor - ilk denemede basimiza gelen buydu.
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
        continue  # hangi bolume ait oldugu anlasilamayan satirlari (or. site menusu) atliyoruz

    # GUNCELLEME: gercek sayfaya bakinca goruldu ki bu "-N.htm" sayfalari zaten
    # maddenin kendi tam metnini (HTML olarak) iceriyor - ayri, tiklanabilir ya da
    # gomulu bir PDF yok (debug ciktisinda 0 <a>/<iframe>/<embed>/<object> cikmasiyla
    # bunu dogruladik). Yani bu sitede madde basina indirilebilir ayri bir PDF dosyasi
    # sunulmuyor - icerigin kendisi bu HTML sayfasi. O yuzden arama mantigini kaldirip
    # dogrudan bu sayfanin ham baytlarini kaydediyoruz (en bastaki basit yaklasim dogruymus).
    icerik_bytes = None
    try:
        icerik_response = requests.get(row["link"], headers=headers, timeout=15)
        icerik_response.raise_for_status()
        icerik_bytes = icerik_response.content
    except requests.RequestException as e:
        print(f"Icerik cekilemedi ({row['link']}): {e}")

    # NOT: tablo adini f-string ile SQL'e gomuyoruz ama bu guvenli, cunku tablo
    # degeri SADECE yukaridaki 4 sabit degerden biri olabilir, disaridan/siteden
    # gelen bir metin degil. title/link/pdf_content gibi gercek veriler ise %s ile,
    # yani parametreli sorgu ile gonderiliyor (SQL injection'a karsi dogru yontem budur).
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

    time.sleep(0.5)   # her madde icin ayri istek attigimizdan, siteyi yormamak icin kisa bir mola

conn.commit()   # buraya kadarki tum INSERT'leri kalici olarak veritabanina yaziyor
print(f"{eklenen} satir veritabanina yazildi.")

cur.close()
conn.close()
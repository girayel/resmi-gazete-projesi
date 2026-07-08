import re
import requests                    # web sayfasini indirmek (HTTP GET istegi atmak) icin
from bs4 import BeautifulSoup      # indirilen ham HTML'i parse edip icinde <a> gibi
                                    # etiketleri kolayca arayabilmek icin
from urllib.parse import urljoin   # sayfadaki linkler bazen goreceli olur (orn. "/eskiler/2026/06/x.htm");
                                    # urljoin bunu ana URL ile birlestirip tam/tiklanabilir link yapar
import csv                         # Python'in kendi built-in CSV yazma modulu, ekstra kurulum istemez


# URL formati: https://www.resmigazete.gov.tr/eskiler/YYYY/AA/YYYYAAGG.htm
# Neden sabit (hardcoded)? ilk adım -> statik bir link verip o gunu cekmek
# Ileride bu satir bir donguye girip her gun icin otomatik degisecek.
URL = "https://www.resmigazete.gov.tr/eskiler/2026/06/20260603.htm"

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
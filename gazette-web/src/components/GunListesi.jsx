import { useState, useEffect, useMemo } from 'react'
import '../Gazete.css'

const SAYFA_BOYUTU = 20
const ARAMA_GECIKME_MS = 300
const AY_ADLARI = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
]
const HAFTA_GUNLERI = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz']
const TARIH_VEYA_SAYI_DESENI = /^\d+(-\d{1,2}(-\d{1,2})?)?$/

function ayParametresi(yil, ay) {
  return `${yil}-${String(ay).padStart(2, '0')}`
}

function GunListesi({ apiUrl, onGunSec, onMaddeSec }) {
  const bugun = useMemo(() => new Date(), [])
  const [secilenYil, setSecilenYil] = useState(bugun.getFullYear())
  const [secilenAy, setSecilenAy] = useState(bugun.getMonth() + 1)

  const [gunHaritasi, setGunHaritasi] = useState({})
  const [yukleniyor, setYukleniyor] = useState(true)
  const [hata, setHata] = useState('')

  const [arama, setArama] = useState('')
  const [aramaGecikmeli, setAramaGecikmeli] = useState('')
  const [aramaSonuclari, setAramaSonuclari] = useState([])
  const [aramaToplamKayit, setAramaToplamKayit] = useState(0)
  const [aramaSayfaNo, setAramaSayfaNo] = useState(0)

  const aramaMetni = aramaGecikmeli.trim()
  const aramaAktif = aramaMetni.length > 0
  const aramaTipi = TARIH_VEYA_SAYI_DESENI.test(aramaMetni) ? 'tarih' : 'kelime'

  useEffect(() => {
    const zamanlayici = setTimeout(() => {
      setAramaGecikmeli(arama)
      setAramaSayfaNo(0)
    }, ARAMA_GECIKME_MS)
    return () => clearTimeout(zamanlayici)
  }, [arama])

  useEffect(() => {
    if (aramaAktif) return
    const controller = new AbortController()
    setYukleniyor(true)
    setHata('')

    const parametreler = new URLSearchParams({
      page: '1',
      pageSize: '31',
      search: ayParametresi(secilenYil, secilenAy),
    })

    fetch(`${apiUrl}/api/gazette-issues?${parametreler}`, { signal: controller.signal })
      .then((cevap) => {
        if (!cevap.ok) throw new Error('yuklenemedi')
        return cevap.json()
      })
      .then((veri) => {
        const harita = {}
        veri.items.forEach((gun) => {
          harita[gun.date] = gun
        })
        setGunHaritasi(harita)
        setYukleniyor(false)
      })
      .catch((hataNesnesi) => {
        if (hataNesnesi.name !== 'AbortError') {
          setHata('Sunucuya bağlanılamadı. API çalışıyor mu?')
          setYukleniyor(false)
        }
      })

    return () => controller.abort()
  }, [apiUrl, secilenYil, secilenAy, aramaAktif])

  useEffect(() => {
    if (!aramaAktif) return
    const controller = new AbortController()
    setYukleniyor(true)
    setHata('')

    const ucNokta = aramaTipi === 'tarih' ? '/api/gazette-issues' : '/api/madde-arama'
    const parametreAdi = aramaTipi === 'tarih' ? 'search' : 'q'
    const parametreler = new URLSearchParams({
      page: String(aramaSayfaNo + 1),
      pageSize: String(SAYFA_BOYUTU),
      [parametreAdi]: aramaMetni,
    })

    fetch(`${apiUrl}${ucNokta}?${parametreler}`, { signal: controller.signal })
      .then((cevap) => {
        if (!cevap.ok) throw new Error('yuklenemedi')
        return cevap.json()
      })
      .then((veri) => {
        setAramaSonuclari(veri.items)
        setAramaToplamKayit(veri.totalCount)
        setYukleniyor(false)
      })
      .catch((hataNesnesi) => {
        if (hataNesnesi.name !== 'AbortError') {
          setHata('Sunucuya bağlanılamadı. API çalışıyor mu?')
          setYukleniyor(false)
        }
      })

    return () => controller.abort()
  }, [apiUrl, aramaAktif, aramaTipi, aramaMetni, aramaSayfaNo])

  const oncekiAy = () => {
    if (secilenAy === 1) {
      setSecilenAy(12)
      setSecilenYil((yil) => yil - 1)
    } else {
      setSecilenAy((ay) => ay - 1)
    }
  }

  const sonrakiAy = () => {
    if (secilenAy === 12) {
      setSecilenAy(1)
      setSecilenYil((yil) => yil + 1)
    } else {
      setSecilenAy((ay) => ay + 1)
    }
  }

  const takvimHucreleri = useMemo(() => {
    const ayinIlkGunu = new Date(secilenYil, secilenAy - 1, 1)
    const ayinGunSayisi = new Date(secilenYil, secilenAy, 0).getDate()
    const haftaBasiKaymasi = (ayinIlkGunu.getDay() + 6) % 7

    const hucreler = []
    for (let i = 0; i < haftaBasiKaymasi; i++) {
      hucreler.push(null)
    }
    for (let gun = 1; gun <= ayinGunSayisi; gun++) {
      const tarihStr = `${secilenYil}-${String(secilenAy).padStart(2, '0')}-${String(gun).padStart(2, '0')}`
      hucreler.push({ gun, tarihStr, gazete: gunHaritasi[tarihStr] })
    }
    while (hucreler.length % 7 !== 0) {
      hucreler.push(null)
    }
    return hucreler
  }, [secilenYil, secilenAy, gunHaritasi])

  const aramaToplamSayfa = Math.max(1, Math.ceil(aramaToplamKayit / SAYFA_BOYUTU))

  return (
    <div className="sayfa takvim-sayfa">
    <h1>Resmî Gazete — {aramaAktif ? 'Arama Sonuçları' : 'Günler'}</h1>
      <input
        className="arama-kutusu"
        type="text"
        placeholder="Tarih (2026-06-03), sayı numarası ya da madde başlığında geçen bir kelime ile ara..."
        value={arama}
        onChange={(olay) => setArama(olay.target.value)}
      />

      {aramaAktif ? (
        <>
          {yukleniyor ? (
            <p className="bos-durum">Yükleniyor...</p>
          ) : hata ? (
            <p className="auth-hata">{hata}</p>
          ) : aramaSonuclari.length === 0 ? (
            <p className="bos-durum">
              {aramaTipi === 'tarih' ? 'Aramaya uyan gün bulunamadı.' : 'Aramaya uyan madde bulunamadı.'}
            </p>
          ) : (
            <ul className="gazete-liste">
              {aramaSonuclari.map((sonuc) =>
                aramaTipi === 'tarih' ? (
                  <li key={sonuc.id}>
                    <button onClick={() => onGunSec(sonuc.date)}>
                      {sonuc.date} {sonuc.issueNumber ? `— Sayı ${sonuc.issueNumber}` : ''}
                    </button>
                  </li>
                ) : (
                  <li key={`${sonuc.bolum}-${sonuc.id}`}>
                    <button onClick={() => onMaddeSec(sonuc)}>
                      <span className="bolum-etiket">{sonuc.date}</span>
                      {sonuc.title}
                    </button>
                  </li>
                )
              )}
            </ul>
          )}

          {aramaToplamSayfa > 1 && (
            <div className="sayfalama">
              <button
                disabled={aramaSayfaNo === 0}
                onClick={() => setAramaSayfaNo(aramaSayfaNo - 1)}
              >
                &larr; Önceki
              </button>
              <span>
                Sayfa {aramaSayfaNo + 1} / {aramaToplamSayfa}
              </span>
              <button
                disabled={aramaSayfaNo >= aramaToplamSayfa - 1}
                onClick={() => setAramaSayfaNo(aramaSayfaNo + 1)}
              >
                Sonraki &rarr;
              </button>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="takvim-baslik">
            <button className="takvim-ok" onClick={oncekiAy}>&larr;</button>
            <span className="takvim-ay-yil">{AY_ADLARI[secilenAy - 1]} {secilenYil}</span>
            <button className="takvim-ok" onClick={sonrakiAy}>&rarr;</button>
          </div>

          {yukleniyor ? (
            <p className="bos-durum">Yükleniyor...</p>
          ) : hata ? (
            <p className="auth-hata">{hata}</p>
          ) : (
            <div className="takvim-izgara">
              {HAFTA_GUNLERI.map((gun) => (
                <div key={gun} className="takvim-hafta-basligi">{gun}</div>
              ))}
              {takvimHucreleri.map((hucre, i) =>
                hucre === null ? (
                  <div key={`bos-${i}`} className="takvim-hucre takvim-hucre-bos" />
                ) : (
                  <button
                    key={hucre.tarihStr}
                    className={hucre.gazete ? 'takvim-hucre takvim-hucre-dolu' : 'takvim-hucre'}
                    disabled={!hucre.gazete}
                    onClick={() => hucre.gazete && onGunSec(hucre.tarihStr)}
                  >
                    <span className="takvim-gun-no">{hucre.gun}</span>
                    {hucre.gazete?.issueNumber && (
                      <span className="takvim-sayi">Sayı {hucre.gazete.issueNumber}</span>
                    )}
                  </button>
                )
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default GunListesi
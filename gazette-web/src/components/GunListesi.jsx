import { useState, useEffect } from 'react'
import '../Gazete.css'

const SAYFA_BOYUTU = 20
// Arama kutusuna yazarken her tuş vuruşunda istek atmamak için bekleme süresi
const ARAMA_GECIKME_MS = 300

function GunListesi({ apiUrl, onGunSec }) {
  const [gunler, setGunler] = useState([])
  const [toplamKayit, setToplamKayit] = useState(0)
  const [yukleniyor, setYukleniyor] = useState(true)
  const [arama, setArama] = useState('')
  const [aramaGecikmeli, setAramaGecikmeli] = useState('')
  const [sayfaNo, setSayfaNo] = useState(0)

  useEffect(() => {
    const zamanlayici = setTimeout(() => {
      setAramaGecikmeli(arama)
      setSayfaNo(0)
    }, ARAMA_GECIKME_MS)
    return () => clearTimeout(zamanlayici)
  }, [arama])

  useEffect(() => {
    const controller = new AbortController()
    setYukleniyor(true)

    const parametreler = new URLSearchParams({
      page: String(sayfaNo + 1),
      pageSize: String(SAYFA_BOYUTU),
    })
    if (aramaGecikmeli.trim()) {
      parametreler.set('search', aramaGecikmeli.trim())
    }

    fetch(`${apiUrl}/api/gazette-issues?${parametreler}`, { signal: controller.signal })
      .then((cevap) => cevap.json())
      .then((veri) => {
        setGunler(veri.items)
        setToplamKayit(veri.totalCount)
        setYukleniyor(false)
      })
      .catch((hata) => {
        if (hata.name !== 'AbortError') throw hata
      })

    return () => controller.abort()
  }, [apiUrl, sayfaNo, aramaGecikmeli])

  const toplamSayfa = Math.max(1, Math.ceil(toplamKayit / SAYFA_BOYUTU))

  return (
    <div className="sayfa">
      <h1>Resmî Gazete — Günler</h1>

      <input
        className="arama-kutusu"
        type="text"
        placeholder="Tarih (2026-06-03) veya sayı numarasına göre ara..."
        value={arama}
        onChange={(olay) => setArama(olay.target.value)}
      />

      {yukleniyor ? (
        <p className="sayfa">Yükleniyor...</p>
      ) : gunler.length === 0 ? (
        <p className="bos-durum">Aramaya uyan gün bulunamadı.</p>
      ) : (
        <ul className="gazete-liste">
          {gunler.map((gun) => (
            <li key={gun.id}>
              <button onClick={() => onGunSec(gun.date)}>
                {gun.date} {gun.issueNumber ? `— Sayı ${gun.issueNumber}` : ''}
              </button>
            </li>
          ))}
        </ul>
      )}

      {toplamSayfa > 1 && (
        <div className="sayfalama">
          <button
            disabled={sayfaNo === 0}
            onClick={() => setSayfaNo(sayfaNo - 1)}
          >
            &larr; Önceki
          </button>
          <span>
            Sayfa {sayfaNo + 1} / {toplamSayfa}
          </span>
          <button
            disabled={sayfaNo >= toplamSayfa - 1}
            onClick={() => setSayfaNo(sayfaNo + 1)}
          >
            Sonraki &rarr;
          </button>
        </div>
      )}
    </div>
  )
}

export default GunListesi

import { useState, useEffect, useMemo } from 'react'
import '../Gazete.css'

const SAYFA_BOYUTU = 20

function GunListesi({ apiUrl, onGunSec }) {
  const [gunler, setGunler] = useState([])
  const [yukleniyor, setYukleniyor] = useState(true)
  const [arama, setArama] = useState('')
  const [sayfaNo, setSayfaNo] = useState(0)

  useEffect(() => {
    fetch(`${apiUrl}/api/gazette-issues`)
      .then((cevap) => cevap.json())
      .then((veri) => {
        setGunler(veri)
        setYukleniyor(false)
      })
  }, [apiUrl])

  const filtrelenmis = useMemo(() => {
    const aramaKucuk = arama.trim().toLowerCase()
    if (!aramaKucuk) return gunler
    return gunler.filter(
      (gun) =>
        gun.date.includes(aramaKucuk) ||
        String(gun.issueNumber ?? '').includes(aramaKucuk)
    )
  }, [gunler, arama])

  const toplamSayfa = Math.max(1, Math.ceil(filtrelenmis.length / SAYFA_BOYUTU))
  const gecerliSayfaNo = Math.min(sayfaNo, toplamSayfa - 1)
  const gosterilenler = filtrelenmis.slice(
    gecerliSayfaNo * SAYFA_BOYUTU,
    gecerliSayfaNo * SAYFA_BOYUTU + SAYFA_BOYUTU
  )

  if (yukleniyor) {
    return <p className="sayfa">Yükleniyor...</p>
  }

  return (
    <div className="sayfa">
      <h1>Resmî Gazete — Günler</h1>

      <input
        className="arama-kutusu"
        type="text"
        placeholder="Tarih (2026-06-03) veya sayı numarasına göre ara..."
        value={arama}
        onChange={(olay) => {
          setArama(olay.target.value)
          setSayfaNo(0)
        }}
      />

      {gosterilenler.length === 0 ? (
        <p className="bos-durum">Aramaya uyan gün bulunamadı.</p>
      ) : (
        <ul className="gazete-liste">
          {gosterilenler.map((gun) => (
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
            disabled={gecerliSayfaNo === 0}
            onClick={() => setSayfaNo(gecerliSayfaNo - 1)}
          >
            &larr; Önceki
          </button>
          <span>
            Sayfa {gecerliSayfaNo + 1} / {toplamSayfa}
          </span>
          <button
            disabled={gecerliSayfaNo >= toplamSayfa - 1}
            onClick={() => setSayfaNo(gecerliSayfaNo + 1)}
          >
            Sonraki &rarr;
          </button>
        </div>
      )}
    </div>
  )
}

export default GunListesi

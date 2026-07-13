import { useState, useEffect, useMemo } from 'react'
import '../Gazete.css'

function MaddeListesi({ apiUrl, tarih, onGeri, onMaddeSec }) {
  const [maddeler, setMaddeler] = useState([])
  const [yukleniyor, setYukleniyor] = useState(true)
  const [arama, setArama] = useState('')

  useEffect(() => {
    setYukleniyor(true)
    fetch(`${apiUrl}/api/gazette-issues/${tarih}`)
      .then((cevap) => cevap.json())
      .then((veri) => {
        setMaddeler(veri)
        setYukleniyor(false)
      })
  }, [apiUrl, tarih])

  const filtrelenmis = useMemo(() => {
    const aramaKucuk = arama.trim().toLocaleLowerCase('tr')
    if (!aramaKucuk) return maddeler
    return maddeler.filter((madde) =>
      madde.title.toLocaleLowerCase('tr').includes(aramaKucuk)
    )
  }, [maddeler, arama])

  return (
    <div className="sayfa">
      <button className="geri-buton" onClick={onGeri}>
        &larr; Günlere dön
      </button>
      <h1>{tarih} — Maddeler</h1>

      {!yukleniyor && maddeler.length > 0 && (
        <input
          className="arama-kutusu"
          type="text"
          placeholder="Başlığa göre ara..."
          value={arama}
          onChange={(olay) => setArama(olay.target.value)}
        />
      )}

      {yukleniyor ? (
        <p className="bos-durum">Yükleniyor...</p>
      ) : maddeler.length === 0 ? (
        <p className="bos-durum">Bu gün için madde bulunamadı.</p>
      ) : filtrelenmis.length === 0 ? (
        <p className="bos-durum">Aramaya uyan madde bulunamadı.</p>
      ) : (
        <ul className="gazete-liste">
          {filtrelenmis.map((madde) => (
            <li key={`${madde.bolum}-${madde.id}`}>
              <button onClick={() => onMaddeSec(madde)}>
                <span className="bolum-etiket">{madde.bolum}</span>
                {madde.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default MaddeListesi

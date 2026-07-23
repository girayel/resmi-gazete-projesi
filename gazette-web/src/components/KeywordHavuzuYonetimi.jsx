import { useState, useEffect } from 'react'
import '../Gazete.css'
import { apiFetch } from '../apiClient'

function KeywordHavuzuYonetimi({ apiUrl, token }) {
  const [havuz, setHavuz] = useState([])
  const [yukleniyor, setYukleniyor] = useState(true)
  const [hata, setHata] = useState('')
  const [yeniKelime, setYeniKelime] = useState('')
  const [ekleniyor, setEkleniyor] = useState(false)
  const [silinenId, setSilinenId] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    setYukleniyor(true)
    setHata('')

    apiFetch(`${apiUrl}/api/keywords`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((cevap) => {
        if (!cevap.ok) throw new Error('yuklenemedi')
        return cevap.json()
      })
      .then(setHavuz)
      .catch((e) => {
        if (e.name !== 'AbortError') setHata('Kelime havuzu yüklenemedi.')
      })
      .finally(() => setYukleniyor(false))

    return () => controller.abort()
  }, [apiUrl, token])

  const kelimeEkle = async (olay) => {
    olay.preventDefault()
    const kelime = yeniKelime.trim()
    if (!kelime) return

    setEkleniyor(true)
    setHata('')
    try {
      const cevap = await apiFetch(`${apiUrl}/api/keywords`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ keyword: kelime }),
      })

      if (!cevap.ok) {
        if (cevap.status === 409) {
          setHata('Bu keyword zaten havuzda var.')
        } else {
          const veri = await cevap.json().catch(() => null)
          setHata(veri?.hata ?? 'Keyword eklenemedi.')
        }
        return
      }

      const yeniKayit = await cevap.json()
      setHavuz((onceki) =>
        [...onceki, yeniKayit].sort((a, b) => a.keyword.localeCompare(b.keyword, 'tr'))
      )
      setYeniKelime('')
    } catch {
      setHata('Sunucuya bağlanılamadı.')
    } finally {
      setEkleniyor(false)
    }
  }

  const kelimeSil = async (keyword) => {
    setSilinenId(keyword.id)
    setHata('')
    try {
      const cevap = await apiFetch(`${apiUrl}/api/keywords/${keyword.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!cevap.ok) {
        setHata('Keyword silinemedi.')
        return
      }

      setHavuz((onceki) => onceki.filter((k) => k.id !== keyword.id))
    } catch {
      setHata('Sunucuya bağlanılamadı.')
    } finally {
      setSilinenId(null)
    }
  }

  return (
    <div className="keyword-havuzu panel-kutu">
      <h2>Kelime Havuzu</h2>

      <form className="keyword-havuz-form" onSubmit={kelimeEkle}>
        <input
          className="arama-kutusu"
          type="text"
          placeholder="Yeni keyword (ör. deprem)"
          value={yeniKelime}
          onChange={(olay) => setYeniKelime(olay.target.value)}
          maxLength={100}
        />
        <button type="submit" className="auth-gonder-buton" disabled={ekleniyor || !yeniKelime.trim()}>
          {ekleniyor ? 'Ekleniyor...' : 'Havuza Ekle'}
        </button>
      </form>

      {hata && <p className="auth-hata">{hata}</p>}

      {yukleniyor ? (
        <p className="bos-durum">Yükleniyor...</p>
      ) : havuz.length === 0 ? (
        <p className="bos-durum">Havuzda hiç keyword yok.</p>
      ) : (
    <div className="keyword-kutu">
        <ul className="keyword-liste">
          {havuz.map((keyword) => (
            <li key={keyword.id} className="keyword-havuz-satir">
              <span>{keyword.keyword}</span>
              <button
                className="keyword-havuz-sil"
                disabled={silinenId === keyword.id}
                onClick={() => kelimeSil(keyword)}
                title="Havuzdan sil"
              >
                {silinenId === keyword.id ? '…' : '✕'}
              </button>
            </li>
          ))}
        </ul>
    </div>
      )}
    </div>
  )
}

export default KeywordHavuzuYonetimi
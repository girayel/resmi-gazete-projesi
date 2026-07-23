import { useState, useEffect } from 'react'
import '../Gazete.css'
import { apiFetch } from '../apiClient'

function KeywordPanel({
  apiUrl,
  token,
  onGeri,
  keywordsYolu = '/api/me/keywords',
  baslik = 'Kelimelerim',
  aciklama = 'Takip etmek istediğin kelimeleri seç. Eşleşen bir Resmî Gazete maddesi yayımlandığında bildirim alacaksın.',
}) {
  const [havuz, setHavuz] = useState([])
  const [secilenIdler, setSecilenIdler] = useState(new Set())
  const [yukleniyor, setYukleniyor] = useState(true)
  const [hata, setHata] = useState('')
  const [islemdeId, setIslemdeId] = useState(null)

  useEffect(() => {
    const headers = { Authorization: `Bearer ${token}` }
    const controller = new AbortController()

    const yukle = async () => {
      setYukleniyor(true)
      setHata('')
      try {
        const [havuzCevap, secilenlerCevap] = await Promise.all([
          apiFetch(`${apiUrl}/api/keywords`, { headers, signal: controller.signal }),
          apiFetch(`${apiUrl}${keywordsYolu}`, { headers, signal: controller.signal }),
        ])
        if (!havuzCevap.ok || !secilenlerCevap.ok) {
          setHata('Kelimeler yüklenemedi.')
          return
        }
        const havuzVeri = await havuzCevap.json()
        const secilenlerVeri = await secilenlerCevap.json()
        setHavuz(havuzVeri)
        setSecilenIdler(new Set(secilenlerVeri.map((k) => k.keywordId)))
      } catch (e) {
        if (e.name !== 'AbortError') setHata('Sunucuya bağlanılamadı.')
      } finally {
        setYukleniyor(false)
      }
    }

    yukle()
    return () => controller.abort()
  }, [apiUrl, token, keywordsYolu])

  const degistir = async (keyword) => {
    const secili = secilenIdler.has(keyword.id)
    setIslemdeId(keyword.id)
    setHata('')

    try {
      const cevap = await apiFetch(
        `${apiUrl}${keywordsYolu}${secili ? `/${keyword.id}` : ''}`,
        {
          method: secili ? 'DELETE' : 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            ...(secili ? {} : { 'Content-Type': 'application/json' }),
          },
          body: secili ? undefined : JSON.stringify({ keywordId: keyword.id }),
        }
      )

      if (!cevap.ok) {
        setHata('İşlem başarısız oldu, tekrar dener misin?')
        return
      }

      setSecilenIdler((onceki) => {
        const yeni = new Set(onceki)
        if (secili) {
          yeni.delete(keyword.id)
        } else {
          yeni.add(keyword.id)
        }
        return yeni
      })
    } catch {
      setHata('Sunucuya bağlanılamadı.')
    } finally {
      setIslemdeId(null)
    }
  }

  return (
    <div className="sayfa">
      <button className="geri-buton" onClick={onGeri}>&larr; Geri</button>
      <h1>{baslik}</h1>
      <p className="keyword-aciklama">{aciklama}</p>

      {yukleniyor ? (
        <p className="sayfa">Yükleniyor...</p>
      ) : (
        <>
          {hata && <p className="auth-hata">{hata}</p>}
    <div className="keyword-kutu">
      <ul className="keyword-liste">
        {havuz.map((keyword) => {
          const secili = secilenIdler.has(keyword.id)
          return (
            <li key={keyword.id}>
              <button
                className={secili ? 'keyword-pill keyword-pill-secili' : 'keyword-pill'}
                disabled={islemdeId === keyword.id}
                onClick={() => degistir(keyword)}
              >
                {secili ? '✓ ' : ''}
                {keyword.keyword}
              </button>
            </li>
          )
        })}
      </ul>
      </div>
        </>
      )}
    </div>
  )
}

export default KeywordPanel

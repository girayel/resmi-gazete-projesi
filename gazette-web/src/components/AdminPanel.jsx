import { useState, useEffect } from 'react'
import KeywordPanel from './KeywordPanel'
import '../Gazete.css'
import KeywordHavuzuYonetimi from './KeywordHavuzuYonetimi'

function AdminPanel({ apiUrl, token, onGeri }) {
  const [kullanicilar, setKullanicilar] = useState([])
  const [yukleniyor, setYukleniyor] = useState(true)
  const [hata, setHata] = useState('')
  const [seciliKullanici, setSeciliKullanici] = useState(null)

  useEffect(() => {
    const controller = new AbortController()

    fetch(`${apiUrl}/api/admin/users`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((cevap) => {
        if (!cevap.ok) {
          throw new Error('yuklenemedi')
        }
        return cevap.json()
      })
      .then(setKullanicilar)
      .catch((e) => {
        if (e.name !== 'AbortError') setHata('Kullanıcı listesi yüklenemedi.')
      })
      .finally(() => setYukleniyor(false))

    return () => controller.abort()
  }, [apiUrl, token])

  if (seciliKullanici) {
    return (
      <KeywordPanel
        apiUrl={apiUrl}
        token={token}
        onGeri={() => setSeciliKullanici(null)}
        keywordsYolu={`/api/admin/users/${seciliKullanici.id}/keywords`}
        baslik={`${seciliKullanici.email} — Kelimeleri`}
        aciklama={`${seciliKullanici.email} (${seciliKullanici.role}) adına keyword atayabilir ya da kaldırabilirsin.`}
      />
    )
  }

  return (
    <div className="sayfa">
      <button className="geri-buton" onClick={onGeri}>&larr; Geri</button>
      <h1>Admin Paneli</h1>
      <KeywordHavuzuYonetimi apiUrl={apiUrl} token={token} />

      <section className="panel-kutu">
        <h2>Kullanıcılar</h2>
        {yukleniyor ? (
          <p className="sayfa">Yükleniyor...</p>
        ) : hata ? (
          <p className="auth-hata">{hata}</p>
        ) : kullanicilar.length === 0 ? (
          <p className="bos-durum">Henüz hiç kullanıcı yok.</p>
        ) : (
          <ul className="gazete-liste">
            {kullanicilar.map((kullanici) => (
              <li key={kullanici.id}>
                <button onClick={() => setSeciliKullanici(kullanici)}>
                  {kullanici.email} <span className="bolum-etiket">{kullanici.role}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

export default AdminPanel

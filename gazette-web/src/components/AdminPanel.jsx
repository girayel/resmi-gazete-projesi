import { useState, useEffect } from 'react'
import KeywordPanel from './KeywordPanel'
import '../Gazete.css'
import KeywordHavuzuYonetimi from './KeywordHavuzuYonetimi'
import { apiFetch } from '../apiClient'

function AdminPanel({ apiUrl, token, onGeri }) {
  const [kullanicilar, setKullanicilar] = useState([])
  const [yukleniyor, setYukleniyor] = useState(true)
  const [hata, setHata] = useState('')
  const [seciliKullanici, setSeciliKullanici] = useState(null)
  const [islemHatasi, setIslemHatasi] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    apiFetch(`${apiUrl}/api/admin/users`, {
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

  const rolDegistir = async (kullanici) => {
    setIslemHatasi('')
    const yeniRol = kullanici.role === 'admin' ? 'user' : 'admin'
    const cevap = await apiFetch(`${apiUrl}/api/admin/users/${kullanici.id}/role`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ role: yeniRol }),
    })
    if (!cevap.ok) {
      const veri = await cevap.json().catch(() => null)
      setIslemHatasi(veri?.hata ?? 'Rol değiştirilemedi.')
      return
    }
    setKullanicilar((liste) => liste.map((k) => (k.id === kullanici.id ? { ...k, role: yeniRol } : k)))
  }

  const durumDegistir = async (kullanici) => {
    setIslemHatasi('')
    const yeniDurum = !kullanici.isActive
    const cevap = await apiFetch(`${apiUrl}/api/admin/users/${kullanici.id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ isActive: yeniDurum }),
    })
    if (!cevap.ok) {
      const veri = await cevap.json().catch(() => null)
      setIslemHatasi(veri?.hata ?? 'Durum değiştirilemedi.')
      return
    }
    setKullanicilar((liste) => liste.map((k) => (k.id === kullanici.id ? { ...k, isActive: yeniDurum } : k)))
  }

  const kullaniciSil = async (kullanici) => {
    setIslemHatasi('')
    if (!window.confirm(`${kullanici.email} kullanicisini silmek istedigine emin misin? Bu islem geri alinamaz.`)) {
      return
    }
    const cevap = await apiFetch(`${apiUrl}/api/admin/users/${kullanici.id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!cevap.ok) {
      const veri = await cevap.json().catch(() => null)
      setIslemHatasi(veri?.hata ?? 'Kullanici silinemedi.')
      return
    }
    setKullanicilar((liste) => liste.filter((k) => k.id !== kullanici.id))
  }

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
        {islemHatasi && <p className="auth-hata">{islemHatasi}</p>}
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
                  {kullanici.email} <span className="bolum-etiket">{kullanici.role}</span>{' '}
                  <span className="bolum-etiket">{kullanici.isActive ? 'aktif' : 'pasif'}</span>
                </button>
                <button onClick={() => rolDegistir(kullanici)}>
                  {kullanici.role === 'admin' ? 'Kullanıcı yap' : 'Admin yap'}
                </button>
                                <button onClick={() => durumDegistir(kullanici)}>
                  {kullanici.isActive ? 'Pasif yap' : 'Aktif yap'}
                </button>
                <button onClick={() => kullaniciSil(kullanici)}>
                  Sil
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
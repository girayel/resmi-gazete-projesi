import { useState } from 'react'
import '../Gazete.css'

function Auth({ apiUrl, onGirisBasarili, onMisafirDevam }) {
  const [mod, setMod] = useState('login')
  const [email, setEmail] = useState('')
  const [sifre, setSifre] = useState('')
  const [hata, setHata] = useState('')
  const [gonderiliyor, setGonderiliyor] = useState(false)

  const gonder = async (olay) => {
    olay.preventDefault()
    setHata('')
    setGonderiliyor(true)

    try {
      const cevap = await fetch(`${apiUrl}/api/auth/${mod === 'login' ? 'login' : 'register'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: sifre }),
      })

      if (!cevap.ok) {
        if (cevap.status === 401) {
          setHata('Email veya şifre hatalı.')
        } else if (cevap.status === 409) {
          setHata('Bu email ile kayıtlı bir kullanıcı zaten var.')
        } else {
          const veri = await cevap.json().catch(() => null)
          setHata(veri?.hata ?? 'Bir hata oluştu.')
        }
        return
      }

      const veri = await cevap.json()
      onGirisBasarili(veri)
    } catch {
      setHata('Sunucuya bağlanılamadı. API çalışıyor mu?')
    } finally {
      setGonderiliyor(false)
    }
  }

  return (
    <div className="sayfa auth-sayfa">
      <h1>Resmî Gazete</h1>

      <div className="auth-sekme">
        <button
          className={mod === 'login' ? 'auth-sekme-aktif' : ''}
          onClick={() => { setMod('login'); setHata('') }}
        >
          Giriş Yap
        </button>
        <button
          className={mod === 'register' ? 'auth-sekme-aktif' : ''}
          onClick={() => { setMod('register'); setHata('') }}
        >
          Kayıt Ol
        </button>
      </div>

      <form className="auth-form" onSubmit={gonder}>
        <input
          className="arama-kutusu"
          type="email"
          placeholder="Email"
          value={email}
          onChange={(olay) => setEmail(olay.target.value)}
          required
        />
        <input
          className="arama-kutusu"
          type="password"
          placeholder="Şifre (en az 6 karakter)"
          value={sifre}
          onChange={(olay) => setSifre(olay.target.value)}
          minLength={6}
          required
        />

        {hata && <p className="auth-hata">{hata}</p>}

        <button type="submit" className="auth-gonder-buton" disabled={gonderiliyor}>
          {gonderiliyor ? 'Gönderiliyor...' : mod === 'login' ? 'Giriş Yap' : 'Kayıt Ol'}
        </button>
      </form>

      <button className="geri-buton" onClick={onMisafirDevam}>
        Misafir olarak devam et →
      </button>
    </div>
  )
}

export default Auth

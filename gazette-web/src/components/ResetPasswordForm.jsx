import { useState } from 'react'
import '../Gazete.css'

function ResetPasswordForm({ apiUrl, token, onTamamlandi }) {
  const [yeniSifre, setYeniSifre] = useState('')
  const [tekrarSifre, setTekrarSifre] = useState('')
  const [hata, setHata] = useState('')
  const [basariMesaji, setBasariMesaji] = useState('')
  const [gonderiliyor, setGonderiliyor] = useState(false)

  const gonder = async (olay) => {
    olay.preventDefault()
    setHata('')

    if (yeniSifre !== tekrarSifre) {
      setHata('Şifreler birbiriyle uyuşmuyor.')
      return
    }

    setGonderiliyor(true)
    try {
      const cevap = await fetch(`${apiUrl}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, newPassword: yeniSifre }),
      })
      const veri = await cevap.json().catch(() => null)

      if (!cevap.ok) {
        setHata(veri?.hata ?? 'Bir hata oluştu.')
        return
      }

      setBasariMesaji(veri?.mesaj ?? 'Şifreniz değiştirildi.')
    } catch {
      setHata('Sunucuya bağlanılamadı. API çalışıyor mu?')
    } finally {
      setGonderiliyor(false)
    }
  }

  return (
    <div className="sayfa auth-sayfa">
      <h1>Şifre Sıfırlama</h1>

      {basariMesaji ? (
        <>
          <p className="auth-basari">{basariMesaji}</p>
          <button className="auth-gonder-buton" onClick={onTamamlandi}>
            Giriş ekranına git
          </button>
        </>
      ) : (
        <form className="auth-form" onSubmit={gonder}>
          <input
            className="arama-kutusu"
            type="password"
            placeholder="Yeni şifre (en az 6 karakter)"
            value={yeniSifre}
            onChange={(olay) => setYeniSifre(olay.target.value)}
            minLength={6}
            required
          />
          <input
            className="arama-kutusu"
            type="password"
            placeholder="Yeni şifre (tekrar)"
            value={tekrarSifre}
            onChange={(olay) => setTekrarSifre(olay.target.value)}
            minLength={6}
            required
          />

          {hata && <p className="auth-hata">{hata}</p>}

          <button type="submit" className="auth-gonder-buton" disabled={gonderiliyor}>
            {gonderiliyor ? 'Gönderiliyor...' : 'Şifreyi Değiştir'}
          </button>
        </form>
      )}
    </div>
  )
}

export default ResetPasswordForm

import { useState } from 'react'
import Auth from './components/Auth'
import GunListesi from './components/GunListesi'
import MaddeListesi from './components/MaddeListesi'
import MaddeDetay from './components/MaddeDetay'
import KeywordPanel from './components/KeywordPanel'
import AdminPanel from './components/AdminPanel'

const API_URL = 'http://localhost:5222'

function App() {
  const [seciliTarih, setSeciliTarih] = useState(null)
  const [seciliMadde, setSeciliMadde] = useState(null)
  const [gorunum, setGorunum] = useState('gazete')
  const [kullanici, setKullanici] = useState(() => {
    const kayitli = localStorage.getItem('gazette_kullanici')
    return kayitli ? JSON.parse(kayitli) : null
  })
  const [misafir, setMisafir] = useState(false)

  const girisYap = (veri) => {
    localStorage.setItem('gazette_kullanici', JSON.stringify(veri))
    setKullanici(veri)
  }

  const cikisYap = () => {
    localStorage.removeItem('gazette_kullanici')
    setKullanici(null)
    setMisafir(false)
    setGorunum('gazete')
  }

  if (!kullanici && !misafir) {
    return (
      <Auth
        apiUrl={API_URL}
        onGirisBasarili={girisYap}
        onMisafirDevam={() => setMisafir(true)}
      />
    )
  }

  return (
    <>
      <div className="ust-bar">
        {kullanici ? (
          <>
            <span>{kullanici.email} ({kullanici.role})</span>
            <button onClick={() => setGorunum(gorunum === 'kelimeler' ? 'gazete' : 'kelimeler')}>
              {gorunum === 'kelimeler' ? 'Gazeteye dön' : 'Kelimelerim'}
            </button>
            {kullanici.role === 'admin' && (
              <button onClick={() => setGorunum(gorunum === 'admin' ? 'gazete' : 'admin')}>
                {gorunum === 'admin' ? 'Gazeteye dön' : 'Kullanıcılar'}
              </button>
            )}
            <button onClick={cikisYap}>Çıkış yap</button>
          </>
        ) : (
          <>
            <span>Misafir modu</span>
            <button onClick={() => setMisafir(false)}>Giriş yap</button>
          </>
        )}
      </div>

      {kullanici && gorunum === 'kelimeler' ? (
        <KeywordPanel apiUrl={API_URL} token={kullanici.token} onGeri={() => setGorunum('gazete')} />
      ) : kullanici && kullanici.role === 'admin' && gorunum === 'admin' ? (
        <AdminPanel apiUrl={API_URL} token={kullanici.token} onGeri={() => setGorunum('gazete')} />
      ) : seciliMadde ? (
        <MaddeDetay madde={seciliMadde} onGeri={() => setSeciliMadde(null)} />
      ) : seciliTarih ? (
        <MaddeListesi
          apiUrl={API_URL}
          tarih={seciliTarih}
          onGeri={() => setSeciliTarih(null)}
          onMaddeSec={setSeciliMadde}
        />
      ) : (
        <GunListesi apiUrl={API_URL} onGunSec={setSeciliTarih} />
      )}
    </>
  )
}

export default App

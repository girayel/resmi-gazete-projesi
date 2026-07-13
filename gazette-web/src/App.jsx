import { useState } from 'react'
import GunListesi from './components/GunListesi'
import MaddeListesi from './components/MaddeListesi'
import MaddeDetay from './components/MaddeDetay'

const API_URL = 'http://localhost:5222'

function App() {
  const [seciliTarih, setSeciliTarih] = useState(null)
  const [seciliMadde, setSeciliMadde] = useState(null)

  if (seciliMadde) {
    return <MaddeDetay madde={seciliMadde} onGeri={() => setSeciliMadde(null)} />
  }

  if (seciliTarih) {
    return (
      <MaddeListesi
        apiUrl={API_URL}
        tarih={seciliTarih}
        onGeri={() => setSeciliTarih(null)}
        onMaddeSec={setSeciliMadde}
      />
    )
  }

  return <GunListesi apiUrl={API_URL} onGunSec={setSeciliTarih} />
}

export default App

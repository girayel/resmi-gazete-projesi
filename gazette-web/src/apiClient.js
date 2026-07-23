export const OturumSonlandirici = 'oturum-sona-erdi'

// Token gerektiren istekler icin fetch sarmalayici: backend 401 donerse
// (token suresi doldu ya da gecersiz), App.jsx'in dinledigi bir olay
// yayinlar ki kullanici otomatik olarak giris ekranina donsun.
export async function apiFetch(url, options = {}) {
  const cevap = await fetch(url, options)
  if (cevap.status === 401 && options.headers?.Authorization) {
    window.dispatchEvent(new CustomEvent(OturumSonlandirici))
  }
  return cevap
}
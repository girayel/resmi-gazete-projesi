import '../Gazete.css'

function MaddeDetay({ madde, onGeri }) {
  return (
    <div className="sayfa">
      <button className="geri-buton" onClick={onGeri}>
        &larr; Maddelere dön
      </button>
      <h1>{madde.title}</h1>
      <p>
        <span className="bolum-etiket">{madde.bolum}</span>
        <a href={madde.link} target="_blank" rel="noreferrer">
          Kaynak sayfa
        </a>
        {' · '}
        <small>{madde.contentType}</small>
      </p>
      <pre className="madde-icerik">{madde.icerik}</pre>
    </div>
  )
}

export default MaddeDetay

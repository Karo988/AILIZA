export default function PiiConsentDialog({ piiData, onConsent, onDismiss }) {
  if (!piiData || !piiData.has_pii) return null

  const consentItems = piiData.items.filter((i) => i.requires_consent)
  if (consentItems.length === 0) return null

  return (
    <div className="pii-dialog-overlay">
      <div className="pii-dialog">
        <div className="pii-dialog-header">
          <span className="pii-icon">🔒</span>
          <h3>Personenbezogene Daten erkannt</h3>
        </div>
        <p className="pii-intro">
          AILIZA hat folgende Daten erkannt. Für die KI-Verarbeitung werden
          diese durch Platzhalter ersetzt (DSGVO Art. 25):
        </p>
        <ul className="pii-list">
          {consentItems.map((item) => (
            <li key={item.type}>
              <strong>{item.type}</strong>
              {item.preview && <span className="pii-preview"> — {item.preview}</span>}
              <span className="pii-count"> ({item.count}×)</span>
            </li>
          ))}
        </ul>
        <p className="pii-note">
          An die KI werden nur Platzhalter wie <code>[[PERSON_1]]</code> gesendet.
          Die Originalwerte bleiben lokal.
        </p>
        <div className="pii-actions">
          <button className="pii-btn consent" onClick={() => onConsent("once")}>
            Einmalig freigeben
          </button>
          <button className="pii-btn dismiss" onClick={onDismiss}>
            Platzhalter behalten
          </button>
        </div>
      </div>
    </div>
  )
}

import { useEffect, useState } from "react"
import "./MemorySettings.css"
import { apiFetch } from "../api"

function display(value, fallback = "Nicht angegeben") {
  if (value === null || value === undefined || value === "") return fallback
  return value
}

function formatDate(value) {
  if (!value) return "Nicht angegeben"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "Nicht angegeben"
  return date.toLocaleDateString("de-DE", { year: "numeric", month: "2-digit", day: "2-digit" })
}

export default function MemorySettings() {
  const [facts, setFacts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [deletingId, setDeletingId] = useState(null)

  async function loadFacts() {
    setLoading(true)
    setError("")
    try {
      const data = await apiFetch("/memory/facts")
      setFacts(Array.isArray(data?.items) ? data.items : [])
    } catch (err) {
      setError(err?.message || "Memory-Facts konnten nicht geladen werden.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFacts()
  }, [])

  async function deleteFact(fact) {
    const title = display(fact.title, "diese Erinnerung")
    const ok = window.confirm(`Diese Erinnerung wirklich loeschen?\n\n${title}`)
    if (!ok) return
    setDeletingId(fact.id)
    setError("")
    try {
      await apiFetch(`/memory/facts/${fact.id}`, { method: "DELETE" })
      await loadFacts()
    } catch (err) {
      setError(err?.message || "Die Erinnerung konnte nicht geloescht werden.")
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="memory-settings" aria-labelledby="memory-settings-title">
      <div className="memory-settings__header">
        <div>
          <h3 id="memory-settings-title">Mein AILIZA-Gedaechtnis</h3>
          <p>Eigene gespeicherte Erinnerungen ansehen und einzeln entfernen.</p>
        </div>
        <button type="button" className="memory-settings__refresh" onClick={loadFacts} disabled={loading}>
          Aktualisieren
        </button>
      </div>

      {loading && <p className="memory-settings__state">Memory-Facts werden geladen ...</p>}
      {error && <p className="memory-settings__error">{error}</p>}
      {!loading && !error && facts.length === 0 && (
        <p className="memory-settings__state">Es sind keine gespeicherten Erinnerungen vorhanden.</p>
      )}

      {!loading && facts.length > 0 && (
        <div className="memory-settings__list">
          {facts.map((fact) => (
            <article className="memory-settings__item" key={fact.id}>
              <div className="memory-settings__item-main">
                <div className="memory-settings__title-row">
                  <h4>{display(fact.title, "Unbenannte Erinnerung")}</h4>
                  <span>{display(fact.scope, "user_memory")}</span>
                </div>
                <p className="memory-settings__content">{display(fact.content)}</p>
                <dl className="memory-settings__meta">
                  <div><dt>Zweck</dt><dd>{display(fact.purpose)}</dd></div>
                  <div><dt>Kategorie</dt><dd>{display(fact.category)}</dd></div>
                  <div><dt>Status</dt><dd>{display(fact.status)}</dd></div>
                  <div><dt>Erstellt</dt><dd>{formatDate(fact.created_at)}</dd></div>
                  <div><dt>Gueltig bis</dt><dd>{formatDate(fact.expires_at)}</dd></div>
                </dl>
              </div>
              <button
                type="button"
                className="memory-settings__delete"
                onClick={() => deleteFact(fact)}
                disabled={deletingId === fact.id}
              >
                {deletingId === fact.id ? "Loesche ..." : "Loeschen"}
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

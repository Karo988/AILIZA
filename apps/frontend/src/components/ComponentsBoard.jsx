import { useEffect, useState } from "react"
import { apiFetch } from "../api"

const tabs = [["recommended", "Empfohlen"], ["active", "Aktiv"], ["blocked", "Nicht einsetzbar"]]

export default function ComponentsBoard() {
  const [board, setBoard] = useState({ recommended: [], active: [], blocked: [] })
  const [tab, setTab] = useState("recommended")
  const [taskPackage, setTaskPackage] = useState("Rechnungen vorbereiten")
  const [dataClass, setDataClass] = useState("public")
  const [error, setError] = useState("")

  useEffect(() => {
    const query = new URLSearchParams({ task_package: taskPackage, data_class: dataClass })
    apiFetch(`/admin/components/board?${query}`)
      .then(setBoard).catch((err) => setError(err.message))
  }, [taskPackage, dataClass])

  return <section className="panel component-board">
    <div className="page-header">
      <p className="eyebrow">Sicher ausgewählt</p>
      <h1>Bausteine</h1>
      <p className="subtitle">AILIZA zeigt nur, was im gewählten Arbeitskontext tatsächlich zulässig ist.</p>
    </div>
    <div className="board-context" aria-label="Arbeitskontext">
      <label>Aufgabenpaket<input value={taskPackage} onChange={e => setTaskPackage(e.target.value)} /></label>
      <label>Datenart<select value={dataClass} onChange={e => setDataClass(e.target.value)}>
        <option value="public">Öffentlich</option><option value="internal">Intern</option>
        <option value="personal_data">Personenbezogen</option><option value="financial">Finanzen</option>
        <option value="hr">Personal</option><option value="special_category">Besonders geschützt</option>
      </select></label>
    </div>
    <div className="board-tabs" role="tablist">
      {tabs.map(([key, label]) => <button key={key} role="tab" aria-selected={tab === key}
        className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label} · {board[key]?.length || 0}</button>)}
    </div>
    {error && <p className="board-error">{error}</p>}
    <div className="component-grid">
      {(board[tab] || []).map(item => <article className="component-card" key={item.candidate_id}>
        <span className={`eligibility eligibility--${item.eligibility}`}>
          {item.eligibility === "eligible" ? "✓ Einsetzbar" : "⛔ Nicht einsetzbar"}
        </span>
        <p className="eyebrow">KI-Modell</p><h3>{item.model_id}</h3><p>{item.provider}</p>
        <p>{item.reason}</p><small>Benchmark: {item.benchmark_version || "noch offen"}</small>
        {item.active && <strong>Aktiv für „{item.task_package}“</strong>}
      </article>)}
      {!error && (board[tab] || []).length === 0 && <p>Für diesen Kontext gibt es hier noch keine Einträge.</p>}
    </div>
    <p className="board-rule">Die Farbe bewertet ausschließlich die Zulässigkeit. Preis, Tempo und Qualität werden getrennt angezeigt.</p>
  </section>
}

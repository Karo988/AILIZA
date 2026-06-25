import { useEffect, useState } from "react"
import { userApi } from "../api/ailizaClient"

export default function RuleManager({ userId }) {
  const [rules, setRules] = useState([])
  const [newRule, setNewRule] = useState("")
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    const data = await userApi.rules(userId)
    setRules(data.rules || [])
    setLoading(false)
  }

  useEffect(() => { load() }, [userId])

  async function addRule() {
    if (!newRule.trim()) return
    await userApi.addRule(userId, newRule.trim())
    setNewRule("")
    load()
  }

  async function deleteRule(ruleId) {
    await userApi.deleteRule(userId, ruleId)
    load()
  }

  if (loading) return <p className="loading-text">Lade Regeln…</p>

  return (
    <div className="rule-manager">
      <h3>Gelernte Regeln</h3>
      <p className="rule-hint">
        AILIZA lernt aus Ihrem Feedback. Diese Regeln werden automatisch auf
        zukünftige Antworten angewendet.
      </p>

      {rules.length === 0 && (
        <p className="rule-empty">Noch keine Regeln — AILIZA lernt durch Korrekturen.</p>
      )}

      <div className="rule-list">
        {rules.map((r) => (
          <div key={r.id} className={`rule-item ${r.active ? "" : "inactive"}`}>
            <div className="rule-text">{r.rule_text}</div>
            <div className="rule-meta">
              <span className="rule-confidence">
                Vertrauen: {Math.round((r.confidence || 0) * 100)}%
              </span>
              <span className="rule-source">{r.source}</span>
              {!r.active && <span className="rule-inactive-badge">Deaktiviert</span>}
            </div>
            <button className="rule-delete" onClick={() => deleteRule(r.id)} title="Regel löschen">
              ✕
            </button>
          </div>
        ))}
      </div>

      <div className="rule-add">
        <input
          value={newRule}
          onChange={(e) => setNewRule(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addRule()}
          placeholder="Neue Regel eingeben, z.B. 'Immer Sie-Form verwenden'"
        />
        <button onClick={addRule} disabled={!newRule.trim()}>Hinzufügen</button>
      </div>
    </div>
  )
}

import { useState, useRef, useEffect } from "react"
import { apiFetch } from "../api"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8001"
const DEBUG_ERRORS = import.meta.env.VITE_DEBUG_ERRORS === "true"

function DiagBlock({ err }) {
  if (!err || !DEBUG_ERRORS) return null
  return (
    <div className="diag-block">
      <p className="diag-title">Technischer Fehler (Testmodus)</p>
      <table className="diag-table">
        <tbody>
          {err.httpStatus && <tr><td>HTTP-Status</td><td><code>{err.httpStatus}</code></td></tr>}
          {err.where && <tr><td>Ort im System</td><td><code>{err.where}</code></td></tr>}
          <tr><td>Fehlermeldung</td><td><code>{err.message}</code></td></tr>
          {err.detail && err.detail !== err.message && (
            <tr><td>Backend-Detail</td><td><code>{err.detail}</code></td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function ScanResult({ scan }) {
  if (!scan) return null
  const ok = scan.allowed
  return (
    <div className={`chat-result ${ok ? "chat-result--ok" : "chat-result--error"}`} style={{ marginTop: "0.75rem" }}>
      <div className="chat-result-icon">{ok ? "✓" : "✗"}</div>
      <div style={{ width: "100%" }}>
        <p className="chat-result-label">Datei-Scan: {ok ? "Zugelassen" : "Blockiert"}</p>
        <p className="chat-result-text">{scan.reason}</p>
        <table className="diag-table" style={{ marginTop: "0.5rem" }}>
          <tbody>
            <tr><td>Typ</td><td><code>{scan.file_type}</code></td></tr>
            <tr><td>Größe</td><td><code>{(scan.size_bytes / 1024).toFixed(1)} KB</code></td></tr>
            <tr><td>Risikoklasse</td><td><code>{scan.highest_risk_class}</code></td></tr>
            <tr><td>Prompt-Injection</td><td><code>{scan.injection_detected ? "⚠ erkannt" : "keine"}</code></td></tr>
            {scan.data_classes?.length > 0 && (
              <tr><td>Datenklassen</td><td><code>{scan.data_classes.join(", ")}</code></td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function AgentChat({ onRunComplete, initialMessages = [], onMessagesChange }) {
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState("")
  const [deepResearch, setDeepResearch] = useState(false)
  const [loading, setLoading] = useState(false)

  const [uploadLoading, setUploadLoading] = useState(false)
  const [scanResult, setScanResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)

  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const bottomRef = useRef(null)

  useEffect(() => { textareaRef.current?.focus() }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages, loading])

  async function handleSend() {
    const raw = input.trim()
    if (!raw || loading) return

    const task = deepResearch
      ? `Führe eine tiefe Recherche durch und erstelle einen strukturierten Bericht: ${raw}`
      : raw

    const userMsg = { role: "user", content: task, id: Date.now() }
    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    onMessagesChange?.(updatedMessages)
    setInput("")
    setLoading(true)

    // History: nur role+content, ohne interne Felder
    const history = updatedMessages.map(m => ({ role: m.role === "error" ? "assistant" : m.role, content: m.content }))

    try {
      const data = await apiFetch("/agent/run", { body: { task, history } })
      if (!data) return

      const status = data?.status
      const content = data?.ai_response || data?.message || "Keine Antwort erhalten."
      const isError = status === "failed" || status === "blocked"

      const assistantMsg = {
        role: isError ? "error" : "assistant",
        content,
        id: Date.now(),
        notice: data?.notice,
        governance_notice: data?.governance_notice,
        draft: data?.draft,
      }
      setMessages(prev => {
        const next = [...prev, assistantMsg]
        onMessagesChange?.(next)
        return next
      })
      onRunComplete?.()
    } catch (err) {
      setMessages(prev => [...prev, {
        role: "error",
        content: `Fehler (HTTP ${err?.httpStatus ?? "unbekannt"})`,
        id: Date.now(),
      }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSend()
  }

  async function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadLoading(true)
    setScanResult(null)
    setUploadError(null)
    const form = new FormData()
    form.append("file", file)
    try {
      const resp = await fetch(`${API_BASE}/documents/scan`, {
        method: "POST",
        credentials: "include",
        body: form,
      })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        const err = new Error(body.detail || body.message || `HTTP ${resp.status}`)
        err.httpStatus = resp.status
        throw err
      }
      setScanResult(await resp.json())
    } catch (err) {
      setUploadError({ httpStatus: err.httpStatus, message: String(err) })
    } finally {
      setUploadLoading(false)
      e.target.value = ""
    }
  }

  return (
    <div className="agent-chat">
      <div className="agent-chat-header">
        <div>
          <h2 className="agent-chat-title">AILIZA</h2>
          <p className="agent-chat-hint">Strg+Enter zum Absenden.</p>
        </div>
        <label className="deep-research-toggle">
          <input type="checkbox" checked={deepResearch} onChange={(e) => setDeepResearch(e.target.checked)} />
          <span>Tiefe Recherche</span>
        </label>
      </div>

      {/* ── Chat-Verlauf ── */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Wie kann ich Ihnen heute helfen?</p>
            <div className="chat-suggestions">
              {[
                "Schreibe eine E-Mail an einen Lieferanten",
                "Was sind meine DSGVO-Pflichten als KMU?",
                "Fasse diesen Text zusammen:",
                "Rechnung analysieren",
              ].map((s) => (
                <button key={s} className="suggestion-chip" onClick={() => {
                  setInput(s)
                  textareaRef.current?.focus()
                }}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg ${msg.role}`}>
            <div className="msg-bubble">
              <pre className="msg-text">{msg.content}</pre>
              {msg.notice && <p className="chat-result-notice">{msg.notice}</p>}
              {msg.governance_notice && <p className="chat-result-notice">{msg.governance_notice}</p>}
              {msg.draft && <p className="chat-result-notice">Entwurf — menschliche Prüfung erforderlich</p>}
            </div>
          </div>
        ))}

        {loading && (
          <div className="chat-msg assistant">
            <div className="msg-bubble loading">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Eingabe ── */}
      <div className="chat-input-row">
        <textarea
          ref={textareaRef}
          className="agent-chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={deepResearch ? "Thema für tiefe Recherche …" : "Nachricht eingeben… (Strg+Enter zum Senden)"}
          rows={2}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          aria-busy={loading}
        >
          {loading ? <span className="agent-chat-spinner" aria-hidden="true" /> : "➤"}
        </button>
      </div>

      {/* ── Datei-Upload ── */}
      <div className="upload-section">
        <p className="upload-label">Datei analysieren</p>
        <p className="upload-hint">Erlaubt: PDF, TXT, MD, HTML, PNG, JPG, GIF, WebP, CSV, JSON, XML</p>
        <label className={`upload-btn${uploadLoading ? " upload-btn--loading" : ""}`}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.md,.html,.htm,.png,.jpg,.jpeg,.gif,.webp,.csv,.json,.xml"
            onChange={handleFileChange}
            disabled={uploadLoading}
            hidden
          />
          {uploadLoading ? <><span className="agent-chat-spinner" aria-hidden="true" /> Wird geprüft …</> : "Datei hochladen & scannen"}
        </label>
        <ScanResult scan={scanResult} />
        {uploadError && <DiagBlock err={uploadError} />}
      </div>
    </div>
  )
}

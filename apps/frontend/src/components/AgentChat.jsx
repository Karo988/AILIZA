import { useState, useRef, useEffect } from "react"
import { apiFetch } from "../api"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8001"

// ── Technische Diagnose (Testumgebung) ─────────────────────────────────────────
function DiagBlock({ err }) {
  if (!err) return null
  return (
    <div className="diag-block">
      <p className="diag-title">Technischer Fehler (Testmodus)</p>
      <table className="diag-table">
        <tbody>
          {err.httpStatus && (
            <tr><td>HTTP-Status</td><td><code>{err.httpStatus}</code></td></tr>
          )}
          {err.where && (
            <tr><td>Ort im System</td><td><code>{err.where}</code></td></tr>
          )}
          <tr><td>Fehlermeldung</td><td><code>{err.message}</code></td></tr>
          {err.detail && err.detail !== err.message && (
            <tr><td>Backend-Detail</td><td><code>{err.detail}</code></td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// ── Antwort-Block ───────────────────────────────────────────────────────────────
function ResultBlock({ result }) {
  if (!result) return null

  if (result.type === "local_only") {
    return (
      <div className="chat-result chat-result--local">
        <div className="chat-result-icon">ℹ</div>
        <div>
          <p className="chat-result-label">Lokaler Modus</p>
          <p className="chat-result-text">{result.message}</p>
          {result.notice && <p className="chat-result-notice">{result.notice}</p>}
        </div>
      </div>
    )
  }

  if (result.type === "error") {
    return (
      <>
        <div className="chat-result chat-result--error">
          <div className="chat-result-icon">!</div>
          <div>
            <p className="chat-result-label">Fehler</p>
            <p className="chat-result-text">{result.userMsg}</p>
          </div>
        </div>
        <DiagBlock err={result.diagErr} />
      </>
    )
  }

  return (
    <div className="chat-result chat-result--ok">
      <div className="chat-result-icon">✓</div>
      <div>
        <p className="chat-result-label">Antwort</p>
        <p className="chat-result-text">{result.message}</p>
        {result.notice && <p className="chat-result-notice">{result.notice}</p>}
      </div>
    </div>
  )
}

// ── Datei-Scan-Ergebnis ────────────────────────────────────────────────────────
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

// ── Fehler für Anzeige aufbereiten ─────────────────────────────────────────────
function buildError(err, where) {
  const status = err?.httpStatus
  const userMsgs = {
    401: "Nicht authentifiziert – bitte neu anmelden.",
    403: "Keine Berechtigung für diese Aktion.",
    500: "Interner Serverfehler – Anfrage wurde nicht ausgeführt.",
  }
  return {
    type: "error",
    userMsg: userMsgs[status] || `Fehler (HTTP ${status ?? "unbekannt"})`,
    diagErr: {
      httpStatus: status,
      where,
      message: err?.message || String(err),
      detail: err?.detail,
    },
  }
}

// ── Hauptkomponente ─────────────────────────────────────────────────────────────
export default function AgentChat({ onRunComplete }) {
  const [input, setInput] = useState("")
  const [deepResearch, setDeepResearch] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const [uploadLoading, setUploadLoading] = useState(false)
  const [scanResult, setScanResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)

  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => { textareaRef.current?.focus() }, [])

  // ── Agent-Run ────────────────────────────────────────────────────────────────
  async function handleSend() {
    const raw = input.trim()
    if (!raw || loading) return

    const task = deepResearch
      ? `Führe eine tiefe Recherche durch und erstelle einen strukturierten Bericht: ${raw}`
      : raw

    setLoading(true)
    setResult(null)

    try {
      const data = await apiFetch("/agent/run", { body: { task } })
      if (!data) return  // 401 → apiFetch leitet weiter

      const status = data?.status
      const message = data?.message || data?.ai_response || "Keine Antwort erhalten."

      if (status === "local_only" || status === "degraded") {
        setResult({ type: "local_only", message, notice: data?.notice })
      } else {
        setResult({ type: "ok", message, notice: data?.notice })
      }
      onRunComplete?.()
    } catch (err) {
      setResult(buildError(err, "POST /agent/run"))
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSend()
  }

  // ── Datei-Upload → /documents/scan ──────────────────────────────────────────
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
        err.detail = body.detail
        throw err
      }
      setScanResult(await resp.json())
    } catch (err) {
      setUploadError(buildError(err, "POST /documents/scan"))
    } finally {
      setUploadLoading(false)
      e.target.value = ""
    }
  }

  function resetAll() {
    setResult(null)
    setScanResult(null)
    setUploadError(null)
    setInput("")
  }

  const hasAnyResult = result || scanResult || uploadError

  return (
    <div className="agent-chat">
      {/* ── Header ── */}
      <div className="agent-chat-header">
        <div>
          <h2 className="agent-chat-title">Frage stellen</h2>
          <p className="agent-chat-hint">Strg+Enter zum Absenden.</p>
        </div>
        <label className="deep-research-toggle">
          <input
            type="checkbox"
            checked={deepResearch}
            onChange={(e) => setDeepResearch(e.target.checked)}
          />
          <span>Tiefe Recherche</span>
        </label>
      </div>

      {/* ── Eingabe ── */}
      <textarea
        ref={textareaRef}
        className="agent-chat-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={
          deepResearch
            ? "Thema für tiefe Recherche …"
            : "Beispiel: Was kannst du für mich tun?"
        }
        rows={4}
        disabled={loading}
        aria-label="Anfrage an AILIZA"
      />

      {/* ── Buttons ── */}
      <div className="agent-chat-actions">
        <button
          className="agent-chat-btn"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          aria-busy={loading}
        >
          {loading && <span className="agent-chat-spinner" aria-hidden="true" />}
          {loading ? "AILIZA denkt …" : deepResearch ? "Recherche starten" : "Senden"}
        </button>

        {hasAnyResult && !loading && (
          <button className="agent-chat-btn agent-chat-btn--ghost" onClick={resetAll}>
            Neue Anfrage
          </button>
        )}
      </div>

      {/* ── Agent-Antwort ── */}
      <ResultBlock result={result} />

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
          {uploadLoading
            ? <><span className="agent-chat-spinner" aria-hidden="true" /> Wird geprüft …</>
            : "Datei hochladen & scannen"
          }
        </label>
        <ScanResult scan={scanResult} />
        {uploadError && <DiagBlock err={uploadError.diagErr} />}
      </div>
    </div>
  )
}

import { useState, useRef, useEffect } from "react"
import { apiFetch } from "../api"

const ERROR_MESSAGES = {
  401: "Bitte melde dich neu an.",
  403: "Dafür brauchst du ein anderes Profil.",
  default: "AILIZA konnte die Anfrage nicht ausführen. Es wurde nichts verändert.",
}

function mapError(err) {
  if (err?.httpStatus === 401) return ERROR_MESSAGES[401]
  if (err?.httpStatus === 403) return ERROR_MESSAGES[403]
  return ERROR_MESSAGES.default
}

function ResultBlock({ result }) {
  if (!result) return null

  if (result.type === "local_only") {
    return (
      <div className="chat-result chat-result--local">
        <div className="chat-result-icon">ℹ</div>
        <div>
          <p className="chat-result-label">Lokaler Modus</p>
          <p className="chat-result-text">{result.message}</p>
        </div>
      </div>
    )
  }

  if (result.type === "error") {
    return (
      <div className="chat-result chat-result--error">
        <div className="chat-result-icon">!</div>
        <div>
          <p className="chat-result-label">Hinweis</p>
          <p className="chat-result-text">{result.message}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="chat-result chat-result--ok">
      <div className="chat-result-icon">✓</div>
      <div>
        <p className="chat-result-label">Antwort</p>
        <p className="chat-result-text">{result.message}</p>
        {result.notice && (
          <p className="chat-result-notice">{result.notice}</p>
        )}
      </div>
    </div>
  )
}

export default function AgentChat() {
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  async function handleSend() {
    const task = input.trim()
    if (!task || loading) return

    setLoading(true)
    setResult(null)

    try {
      const data = await apiFetch("/agent/run", { body: { task } })

      if (!data) {
        // 401 → apiFetch redirects, data is null
        return
      }

      const status = data?.status
      const message = data?.message || data?.ai_response || "Keine Antwort erhalten."

      if (status === "local_only" || status === "degraded") {
        setResult({ type: "local_only", message })
        return
      }

      setResult({ type: "ok", message, notice: data?.notice })
    } catch (err) {
      setResult({ type: "error", message: mapError(err) })
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      handleSend()
    }
  }

  return (
    <div className="agent-chat">
      <h2 className="agent-chat-title">Frage stellen</h2>
      <p className="agent-chat-hint">
        Stelle eine Frage oder gib eine Aufgabe ein. Strg+Enter zum Absenden.
      </p>

      <textarea
        ref={textareaRef}
        className="agent-chat-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Beispiel: Was kannst du für mich tun?"
        rows={4}
        disabled={loading}
        aria-label="Anfrage an AILIZA"
      />

      <div className="agent-chat-actions">
        <button
          className="agent-chat-btn"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          aria-busy={loading}
        >
          {loading ? (
            <span className="agent-chat-spinner" aria-hidden="true" />
          ) : null}
          {loading ? "AILIZA denkt …" : "Senden"}
        </button>

        {result && !loading && (
          <button
            className="agent-chat-btn agent-chat-btn--ghost"
            onClick={() => { setResult(null); setInput("") }}
          >
            Neue Anfrage
          </button>
        )}
      </div>

      <ResultBlock result={result} />
    </div>
  )
}

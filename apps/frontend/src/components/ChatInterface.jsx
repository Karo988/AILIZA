import { useState, useRef, useEffect } from "react"
import { chatApi, feedbackApi } from "../api/ailizaClient"
import PiiConsentDialog from "./PiiConsentDialog"

export default function ChatInterface({ userId, sessionId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [pendingPii, setPendingPii] = useState(null)
  const [pendingMessage, setPendingMessage] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function sendMessage(text) {
    if (!text.trim() || loading) return
    setInput("")
    setLoading(true)

    const userMsg = { role: "user", content: text, id: Date.now() }
    setMessages((prev) => [...prev, userMsg])

    try {
      const res = await chatApi.send(userId, text, conversationId, sessionId)

      if (res.conversation_id) setConversationId(res.conversation_id)

      // PII erkannt → Dialog zeigen
      if (res.pii_detected?.has_pii && res.pii_detected.requires_consent) {
        setPendingPii(res.pii_detected)
        setPendingMessage({ res, text })
        setLoading(false)
        return
      }

      addAssistantMessage(res)
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "error", content: "Verbindungsfehler. Läuft der Backend-Server?", id: Date.now() },
      ])
    }
    setLoading(false)
  }

  function addAssistantMessage(res) {
    const answer = res.ai_response || res.message || "(Keine Antwort)"
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: answer,
        id: Date.now(),
        message_id: res.message_id,
        pii: res.pii_detected,
      },
    ])
  }

  function handlePiiConsent() {
    setPendingPii(null)
    if (pendingMessage) addAssistantMessage(pendingMessage.res)
    setPendingMessage(null)
    setLoading(false)
  }

  function handlePiiDismiss() {
    setPendingPii(null)
    setPendingMessage(null)
    setLoading(false)
  }

  async function sendFeedback(msg, rating) {
    if (msg.message_id) {
      await feedbackApi.send(userId, msg.message_id, rating, "")
    }
    setMessages((prev) =>
      prev.map((m) => (m.id === msg.id ? { ...m, rated: rating } : m))
    )
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className="chat-container">
      <PiiConsentDialog
        piiData={pendingPii}
        onConsent={handlePiiConsent}
        onDismiss={handlePiiDismiss}
      />

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon">💬</div>
            <p>Wie kann ich Ihnen heute helfen?</p>
            <div className="chat-suggestions">
              {[
                "Schreibe eine E-Mail an einen Lieferanten",
                "Was sind meine DSGVO-Pflichten als KMU?",
                "Fasse diesen Text zusammen:",
                "Rechnung analysieren",
              ].map((s) => (
                <button key={s} className="suggestion-chip" onClick={() => sendMessage(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`chat-msg ${msg.role}`}>
            <div className="msg-bubble">
              <pre className="msg-text">{msg.content}</pre>
            </div>
            {msg.role === "assistant" && !msg.rated && (
              <div className="msg-feedback">
                <button onClick={() => sendFeedback(msg, 5)} title="Hilfreich">👍</button>
                <button onClick={() => sendFeedback(msg, 1)} title="Nicht hilfreich">👎</button>
                {msg.pii?.has_pii && (
                  <span className="pii-badge" title="Personenbezogene Daten erkannt und pseudonymisiert">
                    🔒 Datenschutz
                  </span>
                )}
              </div>
            )}
            {msg.rated && (
              <div className="msg-feedback">
                <span className="feedback-done">{msg.rated >= 4 ? "👍 Danke!" : "👎 Notiert."}</span>
              </div>
            )}
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

      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Nachricht eingeben… (Enter zum Senden, Shift+Enter = Zeilenumbruch)"
          disabled={loading}
          rows={1}
        />
        <button
          className="send-btn"
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
        >
          ➤
        </button>
      </div>
    </div>
  )
}

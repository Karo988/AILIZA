const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

async function post(path, body) {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  return r.json()
}

async function get(path) {
  const r = await fetch(BASE + path)
  return r.json()
}

async function del(path) {
  const r = await fetch(BASE + path, { method: "DELETE" })
  return r.json()
}

export const chatApi = {
  send: (user_id, message, conversation_id, session_id) =>
    post("/chat", { user_id, message, conversation_id, session_id }),
  history: (conversation_id) => get(`/chat/${conversation_id}/history`),
  conversations: (user_id) => get(`/users/${user_id}/conversations`),
}

export const agentApi = {
  run: (task, session_id, user_rules) =>
    post("/agent/run", { task, session_id, user_rules }),
}

export const auditApi = {
  list: (limit = 50) => get(`/audit-logs?limit=${limit}`),
}

export const userApi = {
  profile: (user_id) => get(`/users/${user_id}/profile`),
  onboarding: (user_id, display_name, company, language) =>
    post(`/users/${user_id}/onboarding`, { display_name, company, language }),
  rules: (user_id) => get(`/users/${user_id}/rules`),
  addRule: (user_id, rule_text) =>
    post(`/users/${user_id}/rules`, { rule_text, source: "explicit" }),
  deleteRule: (user_id, rule_id) => del(`/users/${user_id}/rules/${rule_id}`),
  deleteAll: (user_id) => del(`/users/${user_id}`),
  export: (user_id) => get(`/users/${user_id}/export`),
}

export const feedbackApi = {
  send: (user_id, message_id, rating, correction) =>
    post("/feedback", { user_id, message_id, rating, correction }),
}

export const keyApi = {
  store: (session_id, provider, api_key) =>
    post("/keys/store", { session_id, provider, api_key }),
  revoke: (session_id) => del(`/keys/${session_id}`),
}

export const complianceApi = {
  processingRecords: (user_id) =>
    get(`/users/${user_id}/processing-records`),
  acknowledge: (record_id) =>
    post(`/compliance/processing-records/${record_id}/acknowledge`, {}),
  agents: () => get("/agents"),
}

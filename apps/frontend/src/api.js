/**
 * AILIZA API-Client
 * ==================
 * - Cookie-basierter Auth-Flow (HttpOnly, SameSite=Strict) als Standard.
 * - Bearer-Token als Fallback fuer API-Clients (wird in sessionStorage, NICHT localStorage gespeichert).
 * - Bei 401: automatischer Redirect zum Login.
 * - Keine Secrets oder Tokens in Logs.
 */

const API_BASE = window?.AILIZA_API || import.meta.env.VITE_API_URL || "https://ailiza.onrender.com"

/**
 * Zentraler Fetch-Wrapper. Cookies werden automatisch vom Browser mitgesendet (credentials: "include").
 * Bei 401 → Login-Redirect.
 */
export async function apiFetch(path, options = {}) {
  const { body, method = body ? "POST" : "GET", headers = {}, ...rest } = options

  const isJson = body && typeof body === "object"
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "include",  // HttpOnly-Cookie wird mitgesendet
    headers: {
      ...(isJson ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: isJson ? JSON.stringify(body) : body,
    ...rest,
  })

  if (response.status === 401) {
    // Token abgelaufen oder kein Cookie → Login
    sessionStorage.removeItem("ailiza_role")
    window.location.href = "/login"
    return null
  }

  if (response.status === 403) {
    const error = await response.json().catch(() => ({}))
    const err = new Error(error.detail || "Keine Berechtigung für diese Aktion.")
    err.httpStatus = 403
    throw err
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    const err = new Error(error.message || error.detail || `HTTP ${response.status}`)
    err.httpStatus = response.status
    throw err
  }

  const ct = response.headers.get("content-type") || ""
  if (ct.includes("application/json")) {
    return response.json()
  }
  return response.text()
}

/**
 * Login: Backend setzt HttpOnly-Cookie und gibt Nutzerinfos zurueck.
 * Wir speichern NUR role + user_id in sessionStorage (kein Token, kein PII).
 */
export async function login(userId, password, tenantId = "default") {
  const data = await apiFetch("/auth/login", {
    body: { user_id: userId, password, tenant_id: tenantId },
  })
  if (data) {
    // Kein user_id in sessionStorage (personenbeziehbar) — nur Rolle fuer UI-Steuerung
    sessionStorage.setItem("ailiza_role", data.role)
  }
  return data
}

/**
 * Logout: Backend loescht Cookie, wir raumen sessionStorage auf.
 */
export async function logout() {
  await apiFetch("/auth/logout", { method: "POST" })
  sessionStorage.removeItem("ailiza_role")
  window.location.href = "/login"
}

/**
 * Prueft ob ein aktiver Session-Cookie vorliegt (via /auth/me).
 * Gibt TokenData zurueck oder null.
 * user_id kommt aus /auth/me (Server), nicht aus sessionStorage.
 */
export async function getSession() {
  try {
    return await apiFetch("/auth/me", { method: "GET" })
  } catch {
    return null
  }
}

export const getRole = () => sessionStorage.getItem("ailiza_role") || "guest"

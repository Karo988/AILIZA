"""
AILIZA Patch Applier
Tausch automatisch die alte run_agent Funktion in main.py gegen die neue Version mit Groq-Integration.
"""
import re
import shutil
from pathlib import Path

MAIN_PY = Path("apps/backend/main.py")

if not MAIN_PY.exists():
    print(f"FEHLER: {MAIN_PY} nicht gefunden! Bist du im C:\\Ailiza Verzeichnis?")
    exit(1)

# Backup
shutil.copy(MAIN_PY, MAIN_PY.with_suffix(".py.backup"))
print(f"Backup erstellt: {MAIN_PY}.backup")

content = MAIN_PY.read_text(encoding="utf-8")

# Neue Funktion
NEW_FUNC = '''@app.post("/agent/run")
def run_agent(payload: AgentRunRequest) -> dict[str, Any]:
    import os, urllib.request, json as _json
    runtime = AgentRuntime()
    result = runtime.run(payload.task)

    # Suchergebnisse aus 'result' Feld extrahieren
    search_text = ""
    if isinstance(result, dict) and "results" in result:
        for step in result.get("results", []):
            data = step.get("result", {}) or step.get("summary", {})
            if isinstance(data, dict):
                if "summary" in data:
                    search_text += str(data["summary"]) + "\\n"
                elif "top_results" in data:
                    for top in data["top_results"][:3]:
                        search_text += f"{top.get('title','')}: {top.get('content','')[:300]}\\n"

    # Groq fragen wenn Key da
    api_key = os.getenv("GROQ_API_KEY")
    if search_text.strip() and api_key:
        sys_prompt = "Du bist AILIZA, ein autonomer KI-Assistent fuer KMU. Antworte kurz und direkt auf Deutsch. Bei einfachen Fragen 1-2 Saetze."
        user_msg = f'Frage: "{payload.task}"\\n\\nSuchergebnis:\\n{search_text}\\n\\nFormuliere eine kurze direkte Antwort.'
        try:
            req_data = _json.dumps({
                "model": "llama3-70b-8192",
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 600,
                "temperature": 0.3,
            }).encode()
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=req_data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                groq_data = _json.loads(r.read())
                answer = groq_data["choices"][0]["message"]["content"]
                result["message"] = answer
                result["ai_response"] = answer
        except Exception as e:
            result["message"] = search_text.strip()
            result["ai_response"] = search_text.strip()
            result["llm_error"] = str(e)
    elif search_text.strip():
        result["message"] = search_text.strip()
        result["ai_response"] = search_text.strip()

    return result'''

# Suche nach run_agent Funktion und ersetze
pattern = re.compile(
    r'@app\.post\("/agent/run"\)\s*\ndef run_agent\([^)]*\)[^:]*:.*?(?=\n@app\.|^@app\.|\Z)',
    re.DOTALL | re.MULTILINE
)

if pattern.search(content):
    new_content = pattern.sub(NEW_FUNC + "\n\n\n", content, count=1)
    MAIN_PY.write_text(new_content, encoding="utf-8")
    print("OK - Patch erfolgreich angewendet!")
    print(f"Datei: {MAIN_PY}")
    # Verifizieren
    check = MAIN_PY.read_text()
    if "groq.com" in check and "GROQ_API_KEY" in check:
        print("OK - Verifiziert: Groq-Integration ist drin!")
    else:
        print("WARNUNG: Konnte Groq-Integration nicht verifizieren")
else:
    print("FEHLER: Konnte run_agent Funktion nicht finden!")
    print("Bitte main.py manuell prüfen.")

from pathlib import Path


FRONTEND = (
    Path(__file__).resolve().parents[1]
    / "apps"
    / "frontend"
    / "index.html"
).read_text(encoding="utf-8")


def test_file_input_is_restricted_to_backend_formats():
    # Karo-Wunsch 2026-07-15 (Stufe 1): Formatliste um reine Text-/Code-
    # Formate ohne neue Abhaengigkeit erweitert. Zip/Bilder/Office-Formate
    # der Stufe 2 duerfen weiterhin NICHT im accept-Attribut stehen.
    accept_start = FRONTEND.index('id="chat-file-input" accept="') + len('id="chat-file-input" accept="')
    accept_end = FRONTEND.index('"', accept_start)
    accepted = FRONTEND[accept_start:accept_end].split(",")
    for ext in (".pdf", ".docx", ".xlsx", ".txt", ".csv",
                ".md", ".html", ".htm", ".rtf",
                ".json", ".xml", ".yaml", ".yml", ".sql",
                ".js", ".ts", ".py", ".css", ".php"):
        assert ext in accepted
    for ext in (".zip", ".png", ".jpg", ".pptx", ".xls"):
        assert ext not in accepted
    assert 'id="chat-file-input" multiple' not in FRONTEND
    assert "CHAT_FILE_MAX_BYTES=10*1024*1024" in FRONTEND


def test_chat_upload_uses_document_agent_endpoint():
    assert "`${API}/documents/agent-run`" in FRONTEND
    assert 'form.append("task",text)' in FRONTEND
    assert 'form.append("file",file,file.name)' in FRONTEND


def test_binary_files_are_not_read_with_file_text():
    start = FRONTEND.index("async function handleChatFileUpload")
    end = FRONTEND.index("async function uploadProjectFile", start)
    upload_block = FRONTEND[start:end]

    assert "file.text()" not in upload_block
    assert "pendingChatFile=file" in upload_block


def test_file_is_preserved_across_login_and_consent_gates():
    assert "let gatedFile=null;" in FRONTEND
    assert "gatedFile=file||null;" in FRONTEND
    assert "const task=gatedTask,aid=gatedConsentApprovalId,file=gatedFile;" in FRONTEND
    assert "const task=gatedTask,file=gatedFile;" in FRONTEND
    assert "runAgent(task,null,aid,file)" in FRONTEND
    assert "runAgent(task,null,undefined,file)" in FRONTEND


def test_consent_id_is_sent_with_document():
    assert 'form.append("consent_approval_id",String(consentApprovalId))' in FRONTEND

def test_project_file_input_click_does_not_bubble_to_card():
    # Karo-Fund 2026-07-15: Der "+ Datei"-Button ruft stopPropagation() nur
    # fuer seinen EIGENEN Klick auf, loest dann aber programmatisch .click()
    # auf dem versteckten <input type="file"> aus. Dieser synthetische Klick
    # ist ein eigenes Event, das erneut durch die Karte (onclick=
    # openProjectChat) blubbert, wenn der Input selbst kein stopPropagation
    # hat - der Chat oeffnete sich dadurch VOR dem Datei-Dialog.
    assert 'class="project-file-input"' in FRONTEND
    idx = FRONTEND.index('class="project-file-input"')
    input_tag_end = FRONTEND.index(">", idx)
    input_tag = FRONTEND[idx:input_tag_end]
    assert 'onclick="event.stopPropagation()"' in input_tag

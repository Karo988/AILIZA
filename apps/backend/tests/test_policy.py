from apps.backend.policy import check_fetch, check_search, check_tool_call, Decision


class TestCheckFetch:
    def test_valid_https_url(self):
        r = check_fetch("https://example.com/page")
        assert r.allowed

    def test_valid_http_url(self):
        r = check_fetch("http://example.com")
        assert r.allowed

    def test_blocks_file_schema(self):
        r = check_fetch("file:///etc/passwd")
        assert r.decision == Decision.BLOCKED

    def test_blocks_ftp_schema(self):
        r = check_fetch("ftp://files.example.com")
        assert r.decision == Decision.BLOCKED

    def test_blocks_localhost(self):
        r = check_fetch("http://localhost/admin")
        assert r.decision == Decision.BLOCKED

    def test_blocks_127(self):
        r = check_fetch("http://127.0.0.1:8080/secret")
        assert r.decision == Decision.BLOCKED

    def test_blocks_private_10(self):
        r = check_fetch("http://10.0.0.5/internal")
        assert r.decision == Decision.BLOCKED

    def test_blocks_private_192(self):
        r = check_fetch("http://192.168.1.1/router")
        assert r.decision == Decision.BLOCKED

    def test_blocks_metadata_aws(self):
        r = check_fetch("http://169.254.169.254/latest/meta-data/")
        assert r.decision == Decision.BLOCKED

    def test_blocks_internal_domain(self):
        r = check_fetch("https://service.internal/api")
        assert r.decision == Decision.BLOCKED

    def test_blocks_too_long_url(self):
        r = check_fetch("https://example.com/" + "a" * 2100)
        assert r.decision == Decision.BLOCKED


class TestCheckSearch:
    def test_normal_query(self):
        r = check_search("Bundesliga Ergebnisse 2025")
        assert r.allowed

    def test_blocks_password_keyword(self):
        r = check_search("find password for admin")
        assert r.decision == Decision.BLOCKED

    def test_blocks_api_key_keyword(self):
        r = check_search("extract api_key from config")
        assert r.decision == Decision.BLOCKED

    def test_blocks_too_long_query(self):
        r = check_search("x " * 300)
        assert r.decision == Decision.BLOCKED

    def test_short_query_ok(self):
        r = check_search("Python FastAPI tutorial")
        assert r.allowed


class TestCheckToolCall:
    def test_fetch_dispatch(self):
        r = check_tool_call("fetch", {"url": "https://example.com"})
        assert r.allowed

    def test_search_dispatch(self):
        r = check_tool_call("search", {"query": "latest AI news"})
        assert r.allowed

    def test_unknown_tool_blocked(self):
        r = check_tool_call("execute_code", {"code": "import os"})
        assert r.decision == Decision.BLOCKED

    def test_blocked_fetch_through_dispatcher(self):
        r = check_tool_call("fetch", {"url": "http://localhost/admin"})
        assert r.decision == Decision.BLOCKED
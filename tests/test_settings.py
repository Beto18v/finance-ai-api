from app.core import settings


def test_cors_origin_regex_missing(monkeypatch):
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    assert settings.cors_origin_regex() is None


def test_cors_origin_regex_present(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"^https://.*\.vercel\.app$")
    assert settings.cors_origin_regex() == r"^https://.*\.vercel\.app$"

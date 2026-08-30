from pydantic import SecretStr
from backend.app.config import Settings


def test_default_settings():
    """Verify default settings structure and sensible defaults."""
    settings = Settings()
    assert settings.APP_NAME == "Secure Enterprise RAG"
    assert settings.ALGORITHM == "HS256"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 60
    assert isinstance(settings.SECRET_KEY, SecretStr)


def test_cors_origins_parsing_from_string():
    """Verify comma-separated CORS string parses into list of origins."""
    settings = Settings(CORS_ORIGINS="http://localhost:3000, https://app.example.com")
    assert settings.CORS_ORIGINS == ["http://localhost:3000", "https://app.example.com"]


def test_cors_origins_parsing_from_list():
    """Verify list of CORS origins passes through intact."""
    settings = Settings(CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"])
    assert settings.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]


def test_secret_key_masking():
    """Verify SecretStr prevents accidental key exposure in str representation."""
    raw_secret = "super-secret-key-12345"
    settings = Settings(SECRET_KEY=raw_secret)
    # The str() or repr() must not expose the raw secret
    assert raw_secret not in str(settings.SECRET_KEY)
    assert settings.SECRET_KEY.get_secret_value() == raw_secret

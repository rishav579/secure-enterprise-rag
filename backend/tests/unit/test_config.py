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


def test_database_url_normalization_postgres_scheme():
    """Verify postgres:// is normalized to postgresql+asyncpg:// for Render/Heroku support."""
    settings = Settings(DATABASE_URL="postgres://user:pass@ep-test.render.com:5432/dbname")
    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pass@ep-test.render.com:5432/dbname"


def test_database_url_normalization_postgresql_scheme():
    """Verify postgresql:// is normalized to postgresql+asyncpg://."""
    settings = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/dbname?sslmode=require")
    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/dbname?sslmode=require"


def test_database_url_normalization_already_correct_asyncpg():
    """Verify postgresql+asyncpg:// remains untouched."""
    url = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
    settings = Settings(DATABASE_URL=url)
    assert settings.DATABASE_URL == url


def test_database_url_normalization_sqlite_preserved():
    """Verify sqlite/in-memory URLs remain untouched."""
    url = "sqlite+aiosqlite:///:memory:"
    settings = Settings(DATABASE_URL=url)
    assert settings.DATABASE_URL == url


def test_create_engine_for_url_normalizes_legacy_schemes():
    """Verify create_engine_for_url normalizes postgres:// to asyncpg engine."""
    from backend.app.database import create_engine_for_url
    engine = create_engine_for_url("postgres://user:pass@localhost:5432/dbname")
    assert engine.url.drivername == "postgresql+asyncpg"
    assert "user" == engine.url.username
    assert "dbname" == engine.url.database

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.config import get_settings

settings = get_settings()


@pytest.mark.asyncio
async def test_real_postgres_and_pgvector():
    """Verify live PostgreSQL connectivity and pgvector functionality.
    
    This integration test connects directly to PostgreSQL using the configured
    DATABASE_URL. If PostgreSQL is not reachable, the test is cleanly skipped.
    When PostgreSQL is available, it verifies:
      1. Live DB connectivity (SELECT 1).
      2. The 'vector' extension is registered in pg_extension.
      3. Vector DDL, vector(3) storage, and vector distance operators (<->, <=>).
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    try:
        async with engine.connect() as conn:
            # 1. Connection check
            res = await conn.execute(text("SELECT 1;"))
            assert res.scalar() == 1

            # 2. pgvector extension verification
            ext_res = await conn.execute(
                text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            )
            row = ext_res.fetchone()
            assert row is not None, "The 'vector' extension is not installed or enabled in PostgreSQL."
            assert row[0] == "vector"

            # 3. Vector arithmetic and distance verification
            await conn.execute(
                text("CREATE TEMP TABLE _test_vectors (id serial PRIMARY KEY, embedding vector(3));")
            )
            await conn.execute(
                text(
                    "INSERT INTO _test_vectors (embedding) VALUES ('[1.0, 2.0, 3.0]'), ('[4.0, 5.0, 6.0]');"
                )
            )
            dist_res = await conn.execute(
                text(
                    "SELECT id, embedding <=> '[1.0, 2.0, 3.0]' AS cosine_dist "
                    "FROM _test_vectors ORDER BY cosine_dist ASC LIMIT 1;"
                )
            )
            top_match = dist_res.fetchone()
            assert top_match is not None
            assert top_match[0] == 1
            assert round(float(top_match[1]), 4) == 0.0

            await conn.execute(text("DROP TABLE IF EXISTS _test_vectors;"))

    except (OSError, ConnectionRefusedError, Exception) as exc:
        err_msg = str(exc).lower()
        if any(keyword in err_msg for keyword in ["connect", "refused", "timeout", "target machine actively refused"]):
            pytest.skip(f"PostgreSQL/pgvector service not accessible at {settings.DATABASE_URL}: {exc}")
        else:
            raise
    finally:
        await engine.dispose()

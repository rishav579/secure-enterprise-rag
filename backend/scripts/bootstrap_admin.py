import asyncio
import logging
import os
import sys

from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.database import AsyncSessionLocal
from backend.app.models.user import User, UserRole

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_bootstrap(
    email: str | None = None,
    password: str | None = None,
    tenant_id: str | None = None,
    session: AsyncSession | None = None,
) -> bool:
    """Idempotently bootstrap or promote an admin user in the database.
    
    Reads credentials from environment variables ADMIN_EMAIL and ADMIN_PASSWORD
    if not explicitly passed. Returns True on success, False on failure.
    """
    admin_email = (email or os.environ.get("ADMIN_EMAIL", "")).strip().lower()
    admin_password = password or os.environ.get("ADMIN_PASSWORD", "")
    admin_tenant = (tenant_id or os.environ.get("ADMIN_TENANT_ID", "default")).strip()

    if not admin_email:
        logger.error("Bootstrap failed: ADMIN_EMAIL environment variable is missing or empty.")
        return False

    if not admin_password:
        logger.error("Bootstrap failed: ADMIN_PASSWORD environment variable is missing or empty.")
        return False

    async def _process_bootstrap(db: AsyncSession) -> bool:
        stmt = select(User).where(User.email == admin_email)
        result = await db.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            updated = False
            if existing_user.role != UserRole.ADMIN:
                existing_user.role = UserRole.ADMIN
                updated = True

            if not existing_user.is_active:
                existing_user.is_active = True
                updated = True

            # Always ensure password is updated to match provided bootstrap password
            existing_user.hashed_password = hash_password(admin_password)

            if updated:
                await db.commit()
                logger.info(f"Successfully promoted existing user '{admin_email}' to ADMIN role.")
            else:
                await db.commit()
                logger.info(f"Admin user '{admin_email}' already exists with ADMIN role. Password synchronized.")

            return True
        else:
            hashed_pw = hash_password(admin_password)
            new_admin = User(
                email=admin_email,
                hashed_password=hashed_pw,
                role=UserRole.ADMIN,
                tenant_id=admin_tenant,
                is_active=True,
            )
            db.add(new_admin)
            await db.commit()
            logger.info(f"Successfully created new ADMIN user '{admin_email}' (tenant: '{admin_tenant}').")
            return True

    if session is not None:
        return await _process_bootstrap(session)

    async with AsyncSessionLocal() as db:
        return await _process_bootstrap(db)



def main() -> None:
    success = asyncio.run(run_bootstrap())
    if not success:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

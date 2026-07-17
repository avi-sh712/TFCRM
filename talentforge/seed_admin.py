"""Create the one-time TalentForge admin account from environment variables."""

from __future__ import annotations

import asyncio
import os

from sqlmodel import select

from talentforge.auth import hash_password, normalize_username
from talentforge.db.database import session_scope
from talentforge.db.models import User, UserRole


async def seed_admin() -> bool:
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    username = os.getenv("ADMIN_USERNAME", email.partition("@")[0])
    if not email or not password:
        return False

    try:
        hashed_password = hash_password(password)
        username = normalize_username(username)
    except ValueError as exc:
        raise RuntimeError(f"ADMIN_PASSWORD is invalid: {exc}") from exc

    async with session_scope() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                username=username,
                hashed_password=hashed_password,
                role=UserRole.ADMIN,
                company_name="TalentForge Admin",
            )
            session.add(user)
            await session.flush()
            user.workspace_id = user.id
            return True
        user.role = UserRole.ADMIN
        user.username = username
        user.hashed_password = hashed_password
        if user.workspace_id is None:
            user.workspace_id = user.id
        return True


if __name__ == "__main__":
    asyncio.run(seed_admin())

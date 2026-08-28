"""创建或更新首个门店管理员账号：python -m scripts.create_admin。"""

import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, async_engine
from app.modules.auth.models import Store, StoreMember
from app.modules.auth.service import hash_password
from app.modules.user.models import User, UserRole, UserStatus


async def create_admin(phone: str, password: str, store_name: str, nickname: str) -> None:
    async with AsyncSessionLocal() as db:
        async with db.begin():
            user = await db.scalar(
                select(User).where(User.phone == phone, User.deleted_at.is_(None))
            )
            if user is None:
                user = User(
                    phone=phone,
                    nickname=nickname,
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                )
                db.add(user)
                await db.flush()
            user.password_hash = hash_password(password)
            user.role = UserRole.ADMIN
            user.status = UserStatus.ACTIVE

            membership = await db.scalar(
                select(StoreMember).where(StoreMember.user_id == user.id)
            )
            if membership is None:
                store = Store(name=store_name)
                db.add(store)
                await db.flush()
                db.add(
                    StoreMember(
                        store_id=store.id,
                        user_id=user.id,
                        role="admin",
                        status="active",
                    )
                )
            else:
                membership.role = "admin"
                membership.status = "active"
        print(f"管理员账号已就绪：{phone}")
    await async_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="创建 TableHub 门店管理员")
    parser.add_argument("--phone", required=True)
    parser.add_argument("--password", help="至少 8 位；省略时安全地交互输入")
    parser.add_argument("--store-name", required=True)
    parser.add_argument("--nickname", default="店长")
    args = parser.parse_args()
    password = args.password or getpass("管理员密码：")
    if len(password) < 8:
        parser.error("密码至少 8 位")
    asyncio.run(create_admin(args.phone, password, args.store_name, args.nickname))


if __name__ == "__main__":
    main()

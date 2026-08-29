from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.database import check_database_connection, close_database_connection
from app.core.exception_handlers import register_exception_handlers


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时验证数据库，关闭时释放连接池。"""

    await check_database_connection()
    yield
    await close_database_connection()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(api_v1_router)
register_exception_handlers(app)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """应用成功启动即表示数据库连接已通过检查。"""

    return {"status": "ok", "database": settings.DATABASE_NAME}


def main():
    """保留命令行入口，推荐通过 uvicorn 启动服务。"""

    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)


if __name__ == "__main__":
    main()

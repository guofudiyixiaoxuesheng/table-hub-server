"""集中读取环境变量并生成类型安全的应用配置。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings"""

    APP_NAME: str = "EMAIL_AGENT"
    DEBUG: bool = True

    # 数据库
    ASYNC_DATABASE_URL: str
    CHECKPOINT_DATABASE_URL: str
    DATABASE_NAME: str = "table_hub"
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "table-hub-server"
    JWT_AUDIENCE: str = "table-hub-web"
    JWT_ACCESS_EXPIRES_MINUTES: int = 15
    JWT_REFRESH_EXPIRES_DAYS: int = 30
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"
    AUTH_COOKIE_DOMAIN: str | None = None
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,"
        "http://192.168.1.116:3000"
    )
    CORS_ORIGIN_REGEX: str | None = (
        r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}):300\d"
    )

    @property
    def database_url(self) -> str:
        """返回指向当前项目独立数据库的异步连接地址。"""

        return (
            make_url(self.ASYNC_DATABASE_URL)
            .set(database=self.DATABASE_NAME)
            .render_as_string(hide_password=False)
        )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    # AI provider
    # LLM_PROVIDER: qwen / deepseek
    LLM_PROVIDER: str = "qwen"
    # IMAGE_GENERATION_PROVIDER: qwen / disabled
    IMAGE_GENERATION_PROVIDER: str = "disabled"
    # true 时只生成并保存最终 Prompt，不会调用外部文生图接口或产生生图费用。
    IMAGE_GENERATION_DRY_RUN: bool = True

    # DeepSeek API
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"

    # Qwen API
    QWEN_API_KEY: str | None = None
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen3.5-omni-plus"
    # 仅用于图片 caption / 视觉规律分析，可与普通聊天模型分开配置。
    QWEN_VISION_MODEL: str = "qwen3.5-omni-plus"
    QWEN_IMAGE_MODEL: str = "wanx2.1-t2i-turbo"
    QWEN_IMAGE_SIZE: str = "1024*1024"
    # 运营海报默认竖版；保留 QWEN_IMAGE_SIZE 供其他方图任务使用。
    QWEN_IMAGE_POSTER_SIZE: str = "720*1280"
    QWEN_IMAGE_API_URL: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    )
    # qwen-image-* 系列使用多模态生成端点，和 wanx2.1 的文生图端点不同。
    QWEN_IMAGE_MULTIMODAL_API_URL: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )
    QWEN_IMAGE_TASK_URL: str = "https://dashscope.aliyuncs.com/api/v1/tasks"
    QWEN_IMAGE_POLL_INTERVAL_SECONDS: float = 2.0
    QWEN_IMAGE_POLL_TIMEOUT_SECONDS: float = 120.0
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 10
    RERANK_ENABLED: bool = True
    RERANK_MODEL: str = "qwen3-rerank"
    RERANK_API_URL: str = ""
    RERANK_TOP_N: int = 5
    RERANK_MIN_SCORE: float = 0.2
    RERANK_TIMEOUT_SECONDS: float = 30.0
    RERANK_INSTRUCT: str = (
        "Given a user question, retrieve passages that contain sufficient "
        "information to answer it."
    )
    SUMMARY_TRIGGER_TOKENS: int = 60_000
    SUMMARY_KEEP_TOKENS: int = 16_000
    SUMMARY_TRIM_TOKENS: int = 50_000
    EVALUATION_WORKER_ENABLED: bool = True
    EVALUATION_WORKER_POLL_SECONDS: float = 2.0
    EVALUATION_JOB_LEASE_SECONDS: int = 600
    EVALUATION_MODEL: str = "qwen-plus"
    EVALUATION_MAX_TOKENS: int = 8192
    EVALUATION_RETRY_MAX_TOKENS: int = 16384
    EVALUATION_METRICS: str = "faithfulness,answer_relevancy,context_utilization"
    EVALUATION_PASS_THRESHOLD: float = 0.7
    SCRIPT_RAG_ANSWER_MAX_TOKENS: int = 6000

    # Langfuse observability
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str | None = None
    LANGFUSE_BASE_URL: str | None = None

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "llama3.2:3b"

    # OSS
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET: str = ""
    OSS_REGION: str = "cn-beijing"
    OSS_ENDPOINT: str = "oss-cn-beijing.aliyuncs.com"
    OSS_PUBLIC_BASE_URL: str = ""
    OSS_PRESIGN_EXPIRES_SECONDS: int = 900
    OSS_MAX_FILES_PER_PACKAGE: int = 500
    OSS_MAX_PACKAGE_SIZE_BYTES: int = 2 * 1024 * 1024 * 1024
    # 其他配置
    REDIS_URL: str = "redis://localhost:6379"

    TAVILY_API_KEY: str | None = None
    # MINERU_TOKEN
    MINERU_TOKEN: str | None = None
    MINERU_BASE_URL: str = "https://mineru.net"
    MINERU_MODEL_VERSION: str = "vlm"
    MINERU_POLL_INTERVAL_SECONDS: float = 2.0
    MINERU_POLL_TIMEOUT_SECONDS: float = 120.0

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]

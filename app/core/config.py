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

    @property
    def database_url(self) -> str:
        """返回指向当前项目独立数据库的异步连接地址。"""

        return (
            make_url(self.ASYNC_DATABASE_URL)
            .set(database=self.DATABASE_NAME)
            .render_as_string(hide_password=False)
        )

    # DeepSeek API
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"

    # Qwen API
    QWEN_API_KEY: str | None = None
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen3.5-omni-plus"
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIMENSION: int = 1024
    EMBEDDING_BATCH_SIZE: int = 10
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
    # 其他配置
    REDIS_URL: str = "redis://localhost:6379"

    TAVILY_API_KEY: str | None = None
    # MINERU_TOKEN
    MINERU_TOKEN: str | None = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]

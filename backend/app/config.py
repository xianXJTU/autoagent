"""应用配置。

所有运行参数集中在这里；密钥只从本地环境或未跟踪的 .env 读取。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "autoagent"
    app_version: str = "0.1.0"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # 数据库
    autoagent_db_host: str = "127.0.0.1"
    autoagent_db_port: int = 3306
    autoagent_db_name: str = "autoagent"
    autoagent_db_test_name: str = "autoagent_test"
    autoagent_db_user: str = "autoagent_app"
    autoagent_db_password: str = ""

    # 对话模型
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"

    # 向量模型
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "qwen3.7-text-embedding-flash"

    # 目录
    workspace_root: Path = BASE_DIR / "workspace"
    data_root: Path = BASE_DIR / "data"
    checkpoint_path: Path = BASE_DIR / "data" / "checkpoints.sqlite"
    chroma_path: Path = BASE_DIR / "data" / "chroma"

    # 业务约束
    max_modules: int = 7
    test_fix_rounds: int = 5
    acceptance_rounds: int = 2
    run_timeout_seconds: int = 7200
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 3
    embedding_batch_size: int = 16

    # 上下文压缩
    model_context_window: int = 1_048_576
    compression_ratio: float = 0.6
    compression_absolute_tokens: int = 200_000
    compression_min_tokens: int = 50_000
    recent_tokens_keep: int = 20_000
    max_compressions_per_session: int = 3

    # 测试开关
    fake_llm: bool = False
    live_tests: bool = Field(default=False)

    @field_validator("max_modules")
    @classmethod
    def _check_max_modules(cls, value: int) -> int:
        if not 1 <= value <= 7:
            raise ValueError("模块数必须在 1 到 7 之间")
        return value

    @field_validator("test_fix_rounds")
    @classmethod
    def _check_fix_rounds(cls, value: int) -> int:
        if not 1 <= value <= 5:
            raise ValueError("修复轮次必须在 1 到 5 之间")
        return value

    @field_validator("acceptance_rounds")
    @classmethod
    def _check_acceptance_rounds(cls, value: int) -> int:
        if not 1 <= value <= 2:
            raise ValueError("验收打回轮次必须在 1 到 2 之间")
        return value

    @field_validator("compression_ratio")
    @classmethod
    def _check_compression_ratio(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("压缩比例必须在 0 到 1 之间")
        return value

    @property
    def database_url(self) -> str:
        return self._build_database_url(self.autoagent_db_name)

    @property
    def test_database_url(self) -> str:
        return self._build_database_url(self.autoagent_db_test_name)

    def _build_database_url(self, database: str) -> str:
        user = quote(self.autoagent_db_user, safe="")
        password = quote(self.autoagent_db_password, safe="")
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.autoagent_db_host}:{self.autoagent_db_port}/{database}?charset=utf8mb4"
        )

    def validate_runtime(self) -> None:
        """启动前检查必需配置；测试替身模式允许缺省密钥。"""
        if self.fake_llm:
            return
        missing: list[str] = []
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if not self.embedding_api_key:
            missing.append("EMBEDDING_API_KEY")
        if not self.embedding_base_url:
            missing.append("EMBEDDING_BASE_URL")
        if missing:
            raise ValueError("缺少必需配置：" + "、".join(missing))

    def ensure_dirs(self) -> None:
        for path in (
            self.workspace_root,
            self.data_root,
            self.chroma_path,
            self.checkpoint_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

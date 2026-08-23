from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOTENV = REPO_ROOT / ".env"

HOST = "127.0.0.1"
PORT = 8000


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    embedding_api_key: str
    embedding_base_url: str
    embedding_model: str
    embedding_dim: int
    data_dir: Path
    host: str = HOST
    port: int = PORT

    @property
    def ai_configured(self) -> bool:
        llm = self.llm_api_key.strip()
        emb = self.embedding_api_key.strip() or llm
        return bool(llm and emb)


def _positive_int(name: str, raw: str | None, default: int) -> int:
    value = default if raw is None or raw.strip() == "" else int(raw)
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return value


def load_settings(environ: dict[str, str] | None = None, *, load_file: bool = False) -> Settings:
    if load_file:
        load_dotenv(DEFAULT_DOTENV, override=True)
    env = os.environ if environ is None else environ
    database_url = (env.get("DATABASE_URL") or "").strip()
    if not database_url:
        raise ConfigError("DATABASE_URL is required")
    data_raw = (env.get("DATA_DIR") or "data").strip()
    data_dir = Path(data_raw)
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir
    llm_key = (env.get("LLM_API_KEY") or "").strip()
    emb_key = (env.get("EMBEDDING_API_KEY") or "").strip()
    return Settings(
        database_url=database_url,
        llm_api_key=llm_key,
        llm_base_url=(
            env.get("LLM_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip(),
        llm_model=(env.get("LLM_MODEL") or "qwen-plus").strip(),
        embedding_api_key=emb_key,
        embedding_base_url=(
            env.get("EMBEDDING_BASE_URL")
            or env.get("LLM_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip(),
        embedding_model=(env.get("EMBEDDING_MODEL") or "text-embedding-v3").strip(),
        embedding_dim=_positive_int("EMBEDDING_DIM", env.get("EMBEDDING_DIM"), 1024),
        data_dir=data_dir,
        host=HOST,
        port=PORT,
    )


_settings: Settings | None = None


def get_settings(*, load_file: bool = True) -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings(load_file=load_file)
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None

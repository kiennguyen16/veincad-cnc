from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VeinCAD CNC"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_upload_mb: int = Field(default=25, ge=1, le=200)
    storage_quota_gb: float = Field(default=9.5, gt=0, le=10)
    storage_dir: Path = Path(__file__).resolve().parents[1] / "storage"
    sample_dir: Path = Path(__file__).resolve().parents[1] / "data" / "samples"
    database_path: Path | None = None
    upload_dir: Path | None = None

    auth_cookie_name: str = "veincad_session"
    auth_cookie_secure: bool = False
    session_days: int = Field(default=7, ge=1, le=90)
    seed_admin_email: str = "slokermoliti@gmail.com"
    seed_admin_password: str = "Test123"
    frontend_url: str = "http://127.0.0.1:3000"
    password_reset_minutes: int = Field(default=30, ge=5, le=1440)

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = "gpt-5.4-nano"
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = "gemini-2.5-flash-lite"

    enable_sam2: bool = False
    sam2_hf_model: str | None = None
    sam2_checkpoint: str | None = None
    sam2_model_cfg: str | None = None
    sam2_device: str = "auto"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VEINCAD_",
        extra="ignore",
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def storage_quota_bytes(self) -> int:
        return int(self.storage_quota_gb * 1_000_000_000)

    @property
    def storage_root(self) -> Path:
        """Stable storage-root name for services that should not depend on legacy directory naming."""
        return self.storage_dir

    @property
    def training_dir(self) -> Path:
        return self.storage_root / "training"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.sample_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_path is None:
        settings.database_path = settings.storage_dir / "veincad.sqlite3"
    if settings.upload_dir is None:
        settings.upload_dir = settings.storage_dir / "uploads" / "slabs"
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.training_dir.mkdir(parents=True, exist_ok=True)
    return settings

from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str = 'sqlite:///./data/github-lens.db'
    data_dir: Path = ROOT / 'data'
    admin_password: str = ''
    cookie_secure: bool = False
    public_base_url: str = ''
    github_token: str = ''
    ocr_provider: str = 'paddle'
    ocr_lang: str = 'ch'
    ai_base_url: str = ''
    ai_api_key: str = ''
    ai_model: str = ''
    ai_daily_limit: int = 100
    agent_auto_research: bool = True
    agent_auto_confirm: bool = True
    research_backend: Literal['computer_use', 'browser', 'deepseek'] = 'browser'
    computer_use_lease_seconds: int = 900
    browser_service_enabled: bool = True
    browser_channel: str = 'chrome'
    browser_headless: bool = True
    browser_request_interval_seconds: int = Field(default=15, ge=1)
    browser_search_interval_seconds: int = Field(default=30, ge=1)
    browser_cooldown_seconds: int = Field(default=900, ge=60)
    browser_max_cooldown_seconds: int = Field(default=21600, ge=60)
    agent_search_daily_limit: int = 50
    ai_search_base_url: str = ''
    worker_enabled: bool = True
    schedule_enabled: bool = True
    max_image_bytes: int = 20 * 1024 * 1024
    max_pixels: int = 50_000_000
    max_batch_files: int = 100


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / 'images').mkdir(exist_ok=True)

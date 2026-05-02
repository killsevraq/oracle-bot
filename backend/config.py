"""Configuration de l'Oracle Bot - chargee depuis l'environnement / .env."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotMode(str, Enum):
    DEMO = "demo"
    PROD = "prod"


class Settings(BaseSettings):
    """Toutes les options du bot. Surchargeables via .env ou variables d'environnement."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Mode et parametres de pari
    mode: BotMode = Field(default=BotMode.DEMO)
    bet_amount: float = Field(default=5.0, ge=0.01)
    stop_loss: float = Field(default=0.0, ge=0.0)
    take_profit: float = Field(default=0.0, ge=0.0)
    demo_starting_balance: float = Field(default=100.0, ge=0.0)

    # Polymarket
    polymarket_market_slug: str = Field(default="")
    polymarket_private_key: str = Field(default="")
    polymarket_funder_address: str = Field(default="")
    polymarket_api_url: str = Field(default="https://clob.polymarket.com")
    polymarket_gamma_url: str = Field(default="https://gamma-api.polymarket.com")

    # Binance
    binance_ws_url: str = Field(default="wss://stream.binance.com:9443/ws/btcusdt@kline_10m")
    binance_rest_url: str = Field(default="https://api.binance.com")
    binance_symbol: str = Field(default="BTCUSDT")

    # Telegram
    telegram_bot_token: str = Field(default="")
    telegram_chat_id: str = Field(default="")

    # API / DB
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    database_url: str = Field(default="sqlite+aiosqlite:///./data/oracle.db")

    # Resolution
    bet_resolution_seconds: int = Field(default=300, ge=10)  # 5 minutes
    candle_interval_seconds: int = Field(default=600, ge=60)  # 10 minutes

    @property
    def is_demo(self) -> bool:
        return self.mode == BotMode.DEMO

    @property
    def is_prod(self) -> bool:
        return self.mode == BotMode.PROD

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token) and bool(self.telegram_chat_id)


settings = Settings()

# S'assurer que le dossier data/ existe pour SQLite
Path("data").mkdir(parents=True, exist_ok=True)

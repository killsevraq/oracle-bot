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
    # NB: Binance ne supporte PAS d'intervalle 10m. Intervalles valides :
    # 1s, 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M.
    # On prend 5m par defaut (= duree du pari BTC 5min).
    binance_ws_url: str = Field(default="wss://stream.binance.com:9443/ws/btcusdt@kline_5m")
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
    # Doit correspondre a l'intervalle de bougie Binance utilise (defaut 5m).
    candle_interval_seconds: int = Field(default=300, ge=60)

    # Filtres de signal (pour eviter de parier sur du bruit)
    # Corps minimum d'une bougie en % du prix (skip si trop petit = quasi-doji).
    # 0.02 % ~ 16 USD sur 78kBTC, ~ 8 USD sur 40kBTC. A monter pour etre plus selectif.
    min_candle_body_pct: float = Field(default=0.02, ge=0.0)
    # Seuil de detection de la tendance Binance en %.
    # 0.02 % ~ 16 USD sur 78kBTC. En dessous => trend FLAT (= signal incertain, on skip).
    binance_trend_threshold_pct: float = Field(default=0.02, ge=0.0)
    # Confirmation post-cloture : on attend N secondes apres la fermeture de la bougie
    # et on verifie que le dernier prix continue dans la direction du signal. 0 = pas de confirmation.
    post_close_confirmation_seconds: float = Field(default=3.0, ge=0.0)

    # Strategie : "candle" (double confirmation bougie + trend Binance, defaut)
    #             "arbitrage" (detecter le retard du carnet Polymarket vs Binance)
    signal_mode: str = Field(default="candle")
    # Seuil d'arbitrage en cents (0..1). Ex: 0.05 = on parie si fair_yes - market_yes > 5 cents.
    arbitrage_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    # Volatilite estimee de BTC sur 5 min en %. 0.20 = 0.2%. Determine la fair value.
    vol_5min_pct: float = Field(default=0.20, gt=0.0)
    # Frequence de poll du carnet Polymarket en mode arbitrage (secondes).
    arbitrage_poll_interval: float = Field(default=2.0, gt=0.0)
    # Slug de la serie Polymarket BTC 5min. Ne pas changer sauf si la serie change de nom.
    polymarket_btc_series_slug: str = Field(default="btc-up-or-down-5m")

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

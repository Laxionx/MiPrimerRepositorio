from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    ANALYSIS_ONLY: bool = True  # Default to analysis-only mode
    LIVE_TRADING: bool = False

    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None

    SYMBOL: str = "EURUSD"
    TIMEFRAME: str = "TIMEFRAME_M5"

    MAX_RISK_PER_TRADE: float = 0.01  # 1%
    MAX_DAILY_LOSS: float = 0.05      # 5%
    MAX_TRADES_PER_DAY: int = 5
    SPREAD_LIMIT: int = 20            # in points/pips
    VOLATILITY_LIMIT: float = 0.005

    REWARD_RISK_RATIO: float = 2.0
    SWING_LOOKBACK: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

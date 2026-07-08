from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import pandas as pd

class MarketDataProvider(ABC):
    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Fetch OHLCV data for a symbol and timeframe."""
        pass

    @abstractmethod
    def get_market_context(self, symbol: str) -> Dict[str, Any]:
        """Fetch current market context (spread, volatility, etc.)."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the data provider is connected."""
        pass

    @abstractmethod
    def get_last_error(self) -> str:
        """Get the last error message."""
        pass

class SignalDetector(ABC):
    @abstractmethod
    def detect_signals(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Process data and detect potential trading signals/setups."""
        pass

class RiskGuard(ABC):
    @abstractmethod
    def validate_setup(self, setup: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate if a setup meets risk management rules. Returns a risk report."""
        pass

class RecommendationPublisher(ABC):
    @abstractmethod
    def publish(self, recommendation: Dict[str, Any]) -> None:
        """Publish the structured recommendation (e.g., to JSON, Log, or MQ)."""
        pass

class Executor(ABC):
    @abstractmethod
    def execute(self, recommendation: Dict[str, Any]) -> bool:
        """Execute a trade based on a recommendation."""
        pass

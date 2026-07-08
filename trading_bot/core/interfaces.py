from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import pandas as pd

class DataProvider(ABC):
    @abstractmethod
    def get_ohlc(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Fetch OHLC data for a symbol and timeframe."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the data provider is connected."""
        pass

    @abstractmethod
    def get_last_error(self) -> str:
        """Get the last error message."""
        pass

class Strategy(ABC):
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Process data and generate a trading signal."""
        pass

class Executor(ABC):
    @abstractmethod
    def execute(self, signal: Dict[str, Any]) -> bool:
        """Execute a trade based on a signal."""
        pass

class RiskManager(ABC):
    @abstractmethod
    def validate_trade(self, signal: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Validate if a trade meets risk management rules."""
        pass

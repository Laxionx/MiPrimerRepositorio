from trading_bot.config.settings import settings
from trading_bot.data.mt5_data import MT5DataProvider
from trading_bot.data.mock_data import MockDataProvider
from trading_bot.core.interfaces import MarketDataProvider
from trading_bot.utils.logger import logger

def get_data_provider() -> MarketDataProvider:
    """
    Factory to instantiate the configured MarketDataProvider.
    Strictly follows the DATA_PROVIDER setting.
    """
    provider_type = settings.DATA_PROVIDER.lower()

    if provider_type == "mt5":
        if not settings.MT5_LOGIN or not settings.MT5_PASSWORD:
            logger.error("MT5_LOGIN and MT5_PASSWORD are required when DATA_PROVIDER=mt5")
            # Fallback is NOT allowed for hardening; we should probably raise or return a null provider
            raise ValueError("MT5 credentials missing while DATA_PROVIDER=mt5")

        return MT5DataProvider(
            login=settings.MT5_LOGIN,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER
        )

    # Default to mock
    logger.info(f"Using MockDataProvider with scenario: {settings.MOCK_SCENARIO}")
    return MockDataProvider(scenario=settings.MOCK_SCENARIO)

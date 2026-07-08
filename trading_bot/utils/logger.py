import logging
import sys

def setup_logger(name: str = "trading_bot", level: int = logging.INFO):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # File handler
        fh = logging.FileHandler("bot.log")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger

logger = setup_logger()

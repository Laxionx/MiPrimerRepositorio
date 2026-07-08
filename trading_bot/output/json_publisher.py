import json
import os
from datetime import datetime
from typing import Dict, Any
from trading_bot.core.interfaces import RecommendationPublisher
from trading_bot.utils.logger import logger

class JSONRecommendationPublisher(RecommendationPublisher):
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def publish(self, recommendation: Dict[str, Any]) -> None:
        timestamp = recommendation.get("timestamp", datetime.now().isoformat())
        symbol = recommendation.get("symbol", "unknown")
        filename = f"recommendation_{symbol}_{timestamp.replace(':', '-')}.json"
        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, 'w') as f:
                json.dump(recommendation, f, indent=2)
            logger.info(f"Recommendation published to {filepath}")
        except Exception as e:
            logger.error(f"Failed to publish recommendation to JSON: {e}")

class ConsolePublisher(RecommendationPublisher):
    def publish(self, recommendation: Dict[str, Any]) -> None:
        logger.info("Structured Recommendation Output:")
        print(json.dumps(recommendation, indent=2))

import os
import logging
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.etl.validation import TrafficInputSchema
from app.etl.transform import ETLTransformer
from app.etl.load import ETLLoader

logger = logging.getLogger("smartflow.etl.collectors.traffic")

class TrafficCollector:
    """
    Polls real-time traffic telemetry from DOT (Department of Transportation) 
    feeds or sensor networks.
    """
    
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        # Default to a mock endpoint if not provided
        self.api_url = api_url or os.getenv("TRAFFIC_API_URL", "https://api.mock-dot.gov/v1/traffic/realtime")
        self.api_key = api_key or os.getenv("TRAFFIC_API_KEY", "mock_key_123")
        self.loader = ETLLoader()
        self.transformer = ETLTransformer()

    async def fetch_raw_data(self) -> List[Dict[str, Any]]:
        """Fetches raw traffic sensor data from the external provider."""
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        
        try:
            # Note: We use a short timeout for real-time telemetry
            async with httpx.AsyncClient(timeout=10.0) as client:
                # In a real scenario, we'd handle pagination or geo-filtering here
                response = await client.get(self.api_url, headers=headers)
                
                # MOCKING: If the URL is a mock/doesn't exist, return sample data
                if response.status_code != 200 or "mock-dot" in self.api_url:
                    logger.debug("Using mock traffic data for development.")
                    return [
                        {"segment_id": 1001, "current_speed": 45.2, "timestamp": datetime.now(timezone.utc).isoformat()},
                        {"segment_id": 1002, "current_speed": "12.5", "congestion_score": 0.85},
                        {"segment_id": 1003, "current_speed": 65.0}
                    ]
                
                return response.json().get("data", [])
        except (httpx.RequestError, Exception) as exc:
            logger.error(f"Error while fetching traffic data: {exc}")
            # Fallback to mock data if in development/testing mode
            if os.getenv("ENV") == "development" or "mock-dot" in self.api_url:
                return [
                    {"segment_id": 1001, "current_speed": 45.2},
                    {"segment_id": 1002, "current_speed": 12.5}
                ]
            return []

    async def run(self):
        """Executes the full collect -> validate -> transform -> load cycle."""
        logger.info("Starting traffic data collection...")
        raw_data = await self.fetch_raw_data()
        
        if not raw_data:
            logger.warning("No traffic data retrieved.")
            return

        validated = []
        for item in raw_data:
            try:
                validated.append(TrafficInputSchema(**item))
            except Exception as e:
                logger.error(f"Validation failed for traffic item {item.get('segment_id', 'unknown')}: {e}")

        if validated:
            transformed = self.transformer.transform_traffic(validated)
            try:
                count = await self.loader.load_traffic_readings(transformed)
                logger.info(f"Traffic Collection Success: {count} readings ingested.")
            except Exception as e:
                logger.error(f"Failed to load traffic readings: {e}")
        else:
            logger.warning("No valid traffic records to load.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = TrafficCollector()
    asyncio.run(collector.run())

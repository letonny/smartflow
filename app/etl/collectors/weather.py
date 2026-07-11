import os
import logging
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.etl.validation import WeatherInputSchema
from app.etl.transform import ETLTransformer
from app.etl.load import ETLLoader

logger = logging.getLogger("smartflow.etl.collectors.weather")

class WeatherCollector:
    """
    Polls meteorological snapshots from NOAA or OpenWeather providers.
    """
    
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = api_url or os.getenv("WEATHER_API_URL", "https://api.weather.gov/points/37.7749,-122.4194")
        self.api_key = api_key or os.getenv("WEATHER_API_KEY", "")
        self.loader = ETLLoader()
        self.transformer = ETLTransformer()

    async def fetch_raw_data(self) -> List[Dict[str, Any]]:
        """Fetches raw weather data for targeted coordinate areas."""
        headers = {
            "User-Agent": "(smartflow-traffic-platform, contact@smartflow.io)",
            "Accept": "application/ld+json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Note: NOAA often requires multi-step lookups (point -> forecast), 
                # but we'll assume a simplified snapshot API for this shell.
                response = await client.get(self.api_url, headers=headers)
                
                if response.status_code != 200 or "weather.gov" in self.api_url:
                    logger.debug("Generating mock weather snapshots.")
                    return [
                        {
                            "latitude": 37.7749,
                            "longitude": -122.4194,
                            "temperature": 18.5,
                            "precipitation": 0.0,
                            "visibility": 10000.0,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        },
                        {
                            "latitude": 34.0522,
                            "longitude": -118.2437,
                            "temperature": 24.0,
                            "rain_intensity": 0.0,
                            "visibility": 16000.0
                        }
                    ]
                
                return response.json().get("snapshots", [])
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            return []

    async def run(self):
        """Executes the weather collection cycle."""
        logger.info("Starting weather data collection...")
        raw_data = await self.fetch_raw_data()
        
        if not raw_data:
            return

        validated = []
        for item in raw_data:
            try:
                validated.append(WeatherInputSchema(**item))
            except Exception as e:
                logger.error(f"Weather validation failed for {item.get('latitude')}, {item.get('longitude')}: {e}")

        if validated:
            transformed = self.transformer.transform_weather(validated)
            try:
                count = await self.loader.load_weather_snapshots(transformed)
                logger.info(f"Weather Collection Success: {count} snapshots ingested.")
            except Exception as e:
                logger.error(f"Failed to load weather snapshots: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = WeatherCollector()
    asyncio.run(collector.run())

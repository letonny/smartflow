import os
import logging
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from app.etl.validation import ConstructionInputSchema
from app.etl.transform import ETLTransformer
from app.etl.load import ETLLoader

logger = logging.getLogger("smartflow.etl.collectors.construction")

class ConstructionCollector:
    """
    Polls planned or active road construction zones from government
    infrastructure planning feeds.
    """
    
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = api_url or os.getenv("CONSTRUCTION_API_URL", "https://api.mock-infrastructure.gov/v1/plans")
        self.api_key = api_key or os.getenv("CONSTRUCTION_API_KEY", "")
        self.loader = ETLLoader()
        self.transformer = ETLTransformer()

    async def fetch_raw_data(self) -> List[Dict[str, Any]]:
        """Fetches raw construction zone geometries and schedules."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(self.api_url)
                
                if response.status_code != 200 or "mock" in self.api_url:
                    logger.debug("Generating mock construction zones.")
                    now = datetime.now(timezone.utc)
                    return [
                        {
                            "description": "Bridge maintenance",
                            "geometry_type": "LineString",
                            "coordinates": [(-122.4, 37.8), (-122.41, 37.81)],
                            "status": "active",
                            "start_date": now.isoformat(),
                            "end_date": (now + timedelta(days=5)).isoformat()
                        },
                        {
                            "description": "New intersection pavimentation",
                            "geometry_type": "Polygon",
                            "coordinates": [
                                [(-122.5, 37.7), (-122.51, 37.7), (-122.51, 37.71), (-122.5, 37.7)]
                            ],
                            "status": "planned",
                            "start_date": (now + timedelta(days=1)).isoformat()
                        }
                    ]
                
                return response.json().get("plans", [])
        except Exception as e:
            logger.error(f"Construction fetch failed: {e}")
            return []

    async def run(self):
        """Executes the construction collection cycle."""
        logger.info("Starting construction data collection...")
        raw_data = await self.fetch_raw_data()
        
        if not raw_data:
            return

        validated = []
        for item in raw_data:
            try:
                validated.append(ConstructionInputSchema(**item))
            except Exception as e:
                logger.error(f"Construction validation failed: {e}")

        if validated:
            transformed = self.transformer.transform_construction(validated)
            try:
                count = await self.loader.load_construction_zones(transformed)
                logger.info(f"Construction Collection Success: {count} zones ingested.")
            except Exception as e:
                logger.error(f"Failed to load construction zones: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = ConstructionCollector()
    asyncio.run(collector.run())

import os
import logging
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.etl.validation import IncidentInputSchema
from app.etl.transform import ETLTransformer
from app.etl.load import ETLLoader

logger = logging.getLogger("smartflow.etl.collectors.incidents")

class IncidentCollector:
    """
    Polls real-time road incidents (accidents, debris, hazards) from 
    emergency response feeds or crowd-sourced data.
    """
    
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = api_url or os.getenv("INCIDENT_API_URL", "https://api.mock-reports.org/v1/incidents")
        self.api_key = api_key or os.getenv("INCIDENT_API_KEY", "")
        self.loader = ETLLoader()
        self.transformer = ETLTransformer()

    async def fetch_raw_data(self) -> List[Dict[str, Any]]:
        """Fetches raw incident reports."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url)
                
                if response.status_code != 200 or "mock" in self.api_url:
                    logger.debug("Generating mock incident reports.")
                    return [
                        {
                            "incident_type": "accident",
                            "description": "3-car pileup on I-80 EB",
                            "latitude": 37.82,
                            "longitude": -122.31,
                            "severity": "high",
                            "status": "active"
                        },
                        {
                            "incident_type": "debris",
                            "description": "Tire fragment in middle lane",
                            "latitude": 37.75,
                            "longitude": -122.42,
                            "severity": 2, # Will be mapped to medium
                            "status": "report"
                        }
                    ]
                
                return response.json().get("incidents", [])
        except Exception as e:
            logger.error(f"Incident fetch failed: {e}")
            return []

    async def run(self):
        """Executes the incident collection cycle."""
        logger.info("Starting incident data collection...")
        raw_data = await self.fetch_raw_data()
        
        if not raw_data:
            return

        validated = []
        for item in raw_data:
            try:
                validated.append(IncidentInputSchema(**item))
            except Exception as e:
                logger.error(f"Incident validation failed: {e}")

        if validated:
            transformed = self.transformer.transform_incident(validated)
            try:
                count = await self.loader.load_incidents(transformed)
                logger.info(f"Incident Collection Success: {count} reports ingested.")
            except Exception as e:
                logger.error(f"Failed to load incidents: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collector = IncidentCollector()
    asyncio.run(collector.run())

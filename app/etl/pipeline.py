import logging
import asyncio
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from app.etl.validation import (
    TrafficInputSchema,
    WeatherInputSchema,
    IncidentInputSchema,
    ConstructionInputSchema
)
from app.etl.transform import ETLTransformer
from app.etl.load import ETLLoader

# Setup basic logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("smartflow.etl.pipeline")

class SmartFlowETLPipeline:
    """
    Orchestrator for the SmartFlow ETL pipeline.
    Accepts raw payloads from external providers, executes structured schema validation,
    transforms payloads into clean PostGIS formats, and handles high-speed batch database loads.
    """
    
    def __init__(self, dsn: Optional[str] = None):
        self.loader = ETLLoader(dsn=dsn)
        self.transformer = ETLTransformer()

    async def ingest_traffic(self, raw_telemetry: List[Dict[str, Any]]) -> int:
        """
        Orchestrates Traffic Telemetry pipeline step.
        """
        logger.info(f"Initiating ingestion for {len(raw_telemetry)} raw traffic payloads.")
        validated_records: List[TrafficInputSchema] = []
        
        # Validation
        for idx, item in enumerate(raw_telemetry):
            try:
                validated = TrafficInputSchema(**item)
                validated_records.append(validated)
            except ValidationError as ve:
                logger.error(
                    f"Traffic validation failed at record {idx} for segment {item.get('segment_id', 'unknown')}. "
                    f"Details: {ve.errors()}"
                )
                # In production, invalid telemetry can be routed to a dead-letter queue (DLQ)
                continue
            except Exception as e:
                logger.error(f"Unexpected error validating traffic record {idx}: {e}", exc_info=True)
                continue

        if not validated_records:
            logger.warning("No valid traffic records remaining to process after validation phase.")
            return 0

        # Transformation
        try:
            transformed_records = self.transformer.transform_traffic(validated_records)
        except Exception as e:
            logger.critical(f"Critical error during traffic transformation: {e}", exc_info=True)
            return 0

        # Load
        try:
            loaded_count = await self.loader.load_traffic_readings(transformed_records)
            logger.info(f"Traffic ingestion complete. Loaded: {loaded_count}/{len(raw_telemetry)} records.")
            return loaded_count
        except Exception as e:
            logger.critical(f"Critical error loading traffic readings to database: {e}", exc_info=True)
            return 0

    async def ingest_weather(self, raw_weather: List[Dict[str, Any]]) -> int:
        """
        Orchestrates Weather Snapshots pipeline step.
        """
        logger.info(f"Initiating ingestion for {len(raw_weather)} raw weather payloads.")
        validated_records: List[WeatherInputSchema] = []
        
        for idx, item in enumerate(raw_weather):
            try:
                validated = WeatherInputSchema(**item)
                validated_records.append(validated)
            except ValidationError as ve:
                logger.error(
                    f"Weather validation failed at record {idx} (Coords: {item.get('latitude')}, {item.get('longitude')}). "
                    f"Details: {ve.errors()}"
                )
                continue
            except Exception as e:
                logger.error(f"Unexpected error validating weather record {idx}: {e}", exc_info=True)
                continue

        if not validated_records:
            logger.warning("No valid weather records remaining to process.")
            return 0

        try:
            transformed_records = self.transformer.transform_weather(validated_records)
        except Exception as e:
            logger.critical(f"Critical error during weather transformation: {e}", exc_info=True)
            return 0

        try:
            loaded_count = await self.loader.load_weather_snapshots(transformed_records)
            logger.info(f"Weather ingestion complete. Loaded: {loaded_count}/{len(raw_weather)} snapshots.")
            return loaded_count
        except Exception as e:
            logger.critical(f"Critical error loading weather to database: {e}", exc_info=True)
            return 0

    async def ingest_incidents(self, raw_incidents: List[Dict[str, Any]]) -> int:
        """
        Orchestrates Live Incidents pipeline step.
        """
        logger.info(f"Initiating ingestion for {len(raw_incidents)} raw incident reports.")
        validated_records: List[IncidentInputSchema] = []
        
        for idx, item in enumerate(raw_incidents):
            try:
                validated = IncidentInputSchema(**item)
                validated_records.append(validated)
            except ValidationError as ve:
                logger.error(
                    f"Incident validation failed at record {idx} of type '{item.get('incident_type', 'unknown')}'. "
                    f"Details: {ve.errors()}"
                )
                continue
            except Exception as e:
                logger.error(f"Unexpected error validating incident record {idx}: {e}", exc_info=True)
                continue

        if not validated_records:
            logger.warning("No valid incident records remaining to process.")
            return 0

        try:
            transformed_records = self.transformer.transform_incident(validated_records)
        except Exception as e:
            logger.critical(f"Critical error during incident transformation: {e}", exc_info=True)
            return 0

        try:
            loaded_count = await self.loader.load_incidents(transformed_records)
            logger.info(f"Incident ingestion complete. Loaded: {loaded_count}/{len(raw_incidents)} reports.")
            return loaded_count
        except Exception as e:
            logger.critical(f"Critical error loading incidents to database: {e}", exc_info=True)
            return 0

    async def ingest_construction(self, raw_construction: List[Dict[str, Any]]) -> int:
        """
        Orchestrates Construction Zones pipeline step.
        """
        logger.info(f"Initiating ingestion for {len(raw_construction)} raw construction zone plans.")
        validated_records: List[ConstructionInputSchema] = []
        
        for idx, item in enumerate(raw_construction):
            try:
                validated = ConstructionInputSchema(**item)
                validated_records.append(validated)
            except ValidationError as ve:
                logger.error(
                    f"Construction zone validation failed at record {idx} ('{item.get('description', 'untitled')}'). "
                    f"Details: {ve.errors()}"
                )
                continue
            except Exception as e:
                logger.error(f"Unexpected error validating construction record {idx}: {e}", exc_info=True)
                continue

        if not validated_records:
            logger.warning("No valid construction records remaining to process.")
            return 0

        try:
            transformed_records = self.transformer.transform_construction(validated_records)
        except Exception as e:
            logger.critical(f"Critical error during construction transformation: {e}", exc_info=True)
            return 0

        try:
            loaded_count = await self.loader.load_construction_zones(transformed_records)
            logger.info(f"Construction ingestion complete. Loaded: {loaded_count}/{len(raw_construction)} zones.")
            return loaded_count
        except Exception as e:
            logger.critical(f"Critical error loading construction zones to database: {e}", exc_info=True)
            return 0

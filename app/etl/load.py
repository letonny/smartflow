import os
import logging
from typing import Any, Dict, List
import asyncpg
from datetime import datetime

logger = logging.getLogger("smartflow.etl.load")

class ETLLoader:
    """
    Handles transactionally safe, high-performance bulk loading of 
    transformed telemetry data into the PostgreSQL/PostGIS database.
    """
    
    def __init__(self, dsn: str = None):
        # Database connection string from environment variables, fallback to standard local Postgres
        self.dsn = dsn or os.getenv(
            "DATABASE_URL", 
            "postgresql://postgres:postgres@localhost:5432/postgres"
        )

    async def _get_connection(self) -> asyncpg.Connection:
        """Establishes and returns an asyncpg database connection."""
        try:
            return await asyncpg.connect(self.dsn)
        except Exception as e:
            logger.critical(f"Critical Database Connection Failure: {e}", exc_info=True)
            raise ConnectionError("Failed to connect to the PostgreSQL database.") from e

    async def load_traffic_readings(self, readings: List[Dict[str, Any]]) -> int:
        """
        Loads transformed traffic readings in a single transactional batch.
        """
        if not readings:
            logger.info("No traffic readings received to load.")
            return 0

        query = """
            INSERT INTO traffic_readings (segment_id, current_speed, congestion_score, timestamp)
            VALUES ($1, $2, $3, $4);
        """
        
        records = [
            (r["segment_id"], r["current_speed"], r["congestion_score"], r["timestamp"])
            for r in readings
        ]
        
        conn = await self._get_connection()
        try:
            async with conn.transaction():
                await conn.executemany(query, records)
                logger.info(f"Successfully batch-inserted {len(readings)} traffic readings.")
                return len(readings)
        except Exception as e:
            logger.error(f"Transaction Rollback: Failed to batch-insert traffic readings. Error: {e}", exc_info=True)
            raise
        finally:
            await conn.close()

    async def load_weather_snapshots(self, snapshots: List[Dict[str, Any]]) -> int:
        """
        Loads transformed weather snapshots. PostGIS Point geometries are compiled from WKT strings.
        """
        if not snapshots:
            logger.info("No weather snapshots received to load.")
            return 0

        query = """
            INSERT INTO weather_snapshots (latitude, longitude, geometry, temperature, rain_intensity, visibility, timestamp)
            VALUES ($1, $2, ST_GeomFromEWKT($3), $4, $5, $6, $7);
        """
        
        records = [
            (
                s["latitude"],
                s["longitude"],
                s["geometry"],  # EWKT e.g. 'SRID=4326;POINT(lng lat)'
                s["temperature"],
                s["rain_intensity"],
                s["visibility"],
                s["timestamp"]
            )
            for s in snapshots
        ]
        
        conn = await self._get_connection()
        try:
            async with conn.transaction():
                await conn.executemany(query, records)
                logger.info(f"Successfully batch-inserted {len(snapshots)} weather snapshots.")
                return len(snapshots)
        except Exception as e:
            logger.error(f"Transaction Rollback: Failed to batch-insert weather snapshots. Error: {e}", exc_info=True)
            raise
        finally:
            await conn.close()

    async def load_incidents(self, incidents: List[Dict[str, Any]]) -> int:
        """
        Loads real-time incident reports. Points are resolved through PostGIS ST_GeomFromEWKT.
        """
        if not incidents:
            logger.info("No incidents received to load.")
            return 0

        query = """
            INSERT INTO incidents (incident_type, description, geometry, severity, status, created_at, updated_at)
            VALUES ($1, $2, ST_GeomFromEWKT($3), $4, $5, $6, $7);
        """
        
        records = [
            (
                i["incident_type"],
                i["description"],
                i["geometry"],  # EWKT Point
                i["severity"],
                i["status"],
                i["created_at"],
                i["updated_at"]
            )
            for i in incidents
        ]
        
        conn = await self._get_connection()
        try:
            async with conn.transaction():
                await conn.executemany(query, records)
                logger.info(f"Successfully batch-inserted {len(incidents)} incidents.")
                return len(incidents)
        except Exception as e:
            logger.error(f"Transaction Rollback: Failed to batch-insert incidents. Error: {e}", exc_info=True)
            raise
        finally:
            await conn.close()

    async def load_construction_zones(self, zones: List[Dict[str, Any]]) -> int:
        """
        Loads construction zones. PostGIS handles spatial parsing of EWKT Polygons or LineStrings.
        """
        if not zones:
            logger.info("No construction zones received to load.")
            return 0

        query = """
            INSERT INTO construction_zones (description, geometry, status, start_date, end_date)
            VALUES ($1, ST_GeomFromEWKT($2), $3, $4, $5);
        """
        
        records = [
            (
                z["description"],
                z["geometry"],  # EWKT LineString or Polygon
                z["status"],
                z["start_date"],
                z["end_date"]
            )
            for z in zones
        ]
        
        conn = await self._get_connection()
        try:
            async with conn.transaction():
                await conn.executemany(query, records)
                logger.info(f"Successfully batch-inserted {len(zones)} construction zones.")
                return len(zones)
        except Exception as e:
            logger.error(f"Transaction Rollback: Failed to batch-insert construction zones. Error: {e}", exc_info=True)
            raise
        finally:
            await conn.close()

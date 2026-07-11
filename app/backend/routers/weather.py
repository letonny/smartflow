import logging
from typing import Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
import asyncpg
from pydantic import BaseModel, Field

from app.backend.main import get_db

logger = logging.getLogger("smartflow.backend.routers.weather")

router = APIRouter()

# --- Pydantic Schema for Response ---

class WeatherResponse(BaseModel):
    id: UUID = Field(..., description="Unique identifier for the weather snapshot.")
    latitude: float = Field(..., description="Latitude coordinate of the weather station.")
    longitude: float = Field(..., description="Longitude coordinate of the weather station.")
    temperature: Optional[float] = Field(None, description="Temperature in Celsius.")
    rain_intensity: Optional[float] = Field(None, description="Precipitation rate in mm/hour.")
    visibility: Optional[float] = Field(None, description="Visibility distance in meters.")
    timestamp: datetime = Field(..., description="Timestamp of when the weather observation was captured.")
    distance_meters: float = Field(..., description="Calculated geodetic distance in meters from the requested point.")


# --- API Endpoint ---

@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="Get nearest weather snapshot",
    description=(
        "Finds the closest recorded weather snapshot relative to the provided GPS coordinates. "
        "Utilizes PostGIS spatial indexing for high-speed nearest-neighbor (<->) sorting, "
        "and computes the geodetic distance in meters using geography casting."
    )
)
async def get_nearest_weather(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude of the location to query."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude of the location to query."),
    conn: asyncpg.Connection = Depends(get_db)
):
    # Retrieve the nearest weather snapshot.
    # Uses the <-> spatial operator for GiST index-accelerated nearest-neighbor lookup,
    # and casts geometry to geography to return exact geodetic distance in meters.
    query = """
        SELECT 
            id, 
            latitude, 
            longitude, 
            temperature, 
            rain_intensity, 
            visibility, 
            timestamp,
            ST_Distance(
                geometry::geography, 
                ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
            ) AS distance_meters
        FROM weather_snapshots
        ORDER BY geometry <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
        LIMIT 1;
    """

    try:
        row = await conn.fetchrow(query, lon, lat)
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No weather snapshots found in the database. Ensure ETL ingestion has run."
            )

        return WeatherResponse(
            id=row["id"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            temperature=row["temperature"],
            rain_intensity=row["rain_intensity"],
            visibility=row["visibility"],
            timestamp=row["timestamp"],
            distance_meters=row["distance_meters"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying nearest weather snapshot: {e}", exc_info=True)
        raise

import json
import logging
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, status
import asyncpg
from pydantic import BaseModel, Field, field_validator

from app.backend.main import get_db

logger = logging.getLogger("smartflow.backend.routers.traffic")

router = APIRouter()

# --- Pydantic Schemas for GeoJSON Serialization ---

class LineStringGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: List[List[float]] = Field(
        ..., 
        description="A list of [longitude, latitude] coordinate pairs defining the road segment path."
    )

class TrafficProperties(BaseModel):
    segment_id: int = Field(..., description="Internal road segment unique identifier.")
    osm_id: int = Field(..., description="OpenStreetMap (OSM) ID for referencing.")
    name: Optional[str] = Field(None, description="Name of the street or highway.")
    speed_limit: Optional[int] = Field(None, description="Speed limit in km/h.")
    length: Optional[float] = Field(None, description="Segment length in meters.")
    current_speed: Optional[float] = Field(None, description="Current estimated average speed in km/h.")
    congestion_score: Optional[float] = Field(None, description="Congestion rating from 0.00 (free flow) to 1.00 (gridlock).")
    reading_timestamp: Optional[datetime] = Field(None, description="Timestamp of the latest traffic reading.")

class TrafficFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: LineStringGeometry
    properties: TrafficProperties

class TrafficFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[TrafficFeature]


# --- API Endpoint ---

@router.get(
    "/current-traffic",
    response_model=TrafficFeatureCollection,
    summary="Fetch current traffic for map viewport",
    description=(
        "Retrieves active traffic telemetry and road segment geometries intersecting with a "
        "geospatial viewport bounding box (min_lon, min_lat, max_lon, max_lat). "
        "Utilizes a PostGIS ST_Intersects index query combined with a LATERAL JOIN for high-speed lookup "
        "of the latest historical reading."
    )
)
async def get_current_traffic(
    min_lon: float = Query(..., ge=-180.0, le=180.0, description="Minimum longitude of the bounding box viewport."),
    min_lat: float = Query(..., ge=-90.0, le=90.0, description="Minimum latitude of the bounding box viewport."),
    max_lon: float = Query(..., ge=-180.0, le=180.0, description="Maximum longitude of the bounding box viewport."),
    max_lat: float = Query(..., ge=-90.0, le=90.0, description="Maximum latitude of the bounding box viewport."),
    conn: asyncpg.Connection = Depends(get_db)
):
    # Basic input checks
    if min_lon >= max_lon:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_lon must be strictly less than max_lon."
        )
    if min_lat >= max_lat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_lat must be strictly less than max_lat."
        )

    # PostGIS ST_Intersects query with ST_MakeEnvelope
    # Combined with LATERAL join for fast index-driven fetching of the latest reading
    query = """
        SELECT 
            s.id AS segment_id, 
            s.osm_id, 
            s.name, 
            ST_AsGeoJSON(s.geometry) AS geometry_json, 
            s.speed_limit, 
            s.length,
            r.current_speed, 
            r.congestion_score, 
            r.timestamp AS reading_timestamp
        FROM road_segments s
        LEFT JOIN LATERAL (
            SELECT current_speed, congestion_score, timestamp
            FROM traffic_readings
            WHERE segment_id = s.id
            ORDER BY timestamp DESC
            LIMIT 1
        ) r ON TRUE
        WHERE ST_Intersects(
            s.geometry, 
            ST_MakeEnvelope($1, $2, $3, $4, 4326)
        );
    """

    try:
        rows = await conn.fetch(query, min_lon, min_lat, max_lon, max_lat)
        
        features = []
        for row in rows:
            # Parse GeoJSON string to Python dict for geometry serialization
            try:
                geom_dict = json.loads(row["geometry_json"])
            except (TypeError, ValueError) as json_err:
                logger.error(f"Failed to parse LineString geometry for segment {row['segment_id']}: {json_err}")
                continue

            # Build properties block
            properties = TrafficProperties(
                segment_id=row["segment_id"],
                osm_id=row["osm_id"],
                name=row["name"],
                speed_limit=row["speed_limit"],
                length=row["length"],
                current_speed=row["current_speed"],
                congestion_score=float(row["congestion_score"]) if row["congestion_score"] is not None else None,
                reading_timestamp=row["reading_timestamp"]
            )

            # Assemble GeoJSON Feature
            feature = TrafficFeature(
                geometry=LineStringGeometry(**geom_dict),
                properties=properties
            )
            features.append(feature)

        return TrafficFeatureCollection(features=features)

    except Exception as e:
        logger.error(f"Error querying current traffic: {e}", exc_info=True)
        # Exception handler in main.py will map low-level database errors, but let's re-raise 
        raise

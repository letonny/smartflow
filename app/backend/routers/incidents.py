import json
import logging
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
import asyncpg
from pydantic import BaseModel, Field

from app.backend.main import get_db

logger = logging.getLogger("smartflow.backend.routers.incidents")

router = APIRouter()

# --- Pydantic Schemas for GeoJSON Serialization ---

class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: List[float] = Field(
        ..., 
        description="A [longitude, latitude] coordinate pair representing the incident point."
    )

class IncidentProperties(BaseModel):
    id: UUID = Field(..., description="Unique database identifier of the incident.")
    incident_type: str = Field(..., description="Category of the incident (e.g., accident, congestion, debris).")
    description: Optional[str] = Field(None, description="Detailed text description of the disruption.")
    severity: str = Field(..., description="Incident severity: low, medium, high, or critical.")
    status: str = Field(..., description="Current state of the incident (active, resolved, cleared).")
    created_at: datetime = Field(..., description="Timestamp of when the incident was registered.")
    updated_at: datetime = Field(..., description="Timestamp of the latest incident status update.")

class IncidentFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: IncidentProperties

class IncidentFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[IncidentFeature]


# --- API Endpoint ---

@router.get(
    "/incidents",
    response_model=IncidentFeatureCollection,
    summary="Fetch active incidents",
    description=(
        "Retrieves active road disruptions (accidents, debris, vehicle breakdowns). "
        "Supports optional filtering by severity and bounding box viewport coordinates. "
        "Outputs standard GeoJSON Point features."
    )
)
async def get_active_incidents(
    severity: Optional[str] = Query(
        None, 
        regex="^(low|medium|high|critical)$", 
        description="Filter by incident severity."
    ),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Minimum viewport longitude."),
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Minimum viewport latitude."),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Maximum viewport longitude."),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Maximum viewport latitude."),
    conn: asyncpg.Connection = Depends(get_db)
):
    # Assemble the dynamic query conditions and arguments list
    conditions = ["status = 'active'"]
    args = []
    arg_idx = 1

    if severity:
        conditions.append(f"severity = ${arg_idx}")
        args.append(severity)
        arg_idx += 1

    # Apply bounding box filter if all viewport parameters are supplied
    bbox_active = all(v is not None for v in (min_lon, min_lat, max_lon, max_lat))
    if bbox_active:
        # Validate bounding box boundaries
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

        conditions.append(f"ST_Intersects(geometry, ST_MakeEnvelope(${arg_idx}, ${arg_idx+1}, ${arg_idx+2}, ${arg_idx+3}, 4326))")
        args.extend([min_lon, min_lat, max_lon, max_lat])
        arg_idx += 4
    elif any(v is not None for v in (min_lon, min_lat, max_lon, max_lat)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="To apply spatial viewport filtering, all four bbox coordinates must be provided: min_lon, min_lat, max_lon, max_lat."
        )

    # Build and execute the SQL query
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT 
            id, 
            incident_type, 
            description, 
            ST_AsGeoJSON(geometry) AS geometry_json, 
            severity, 
            status, 
            created_at, 
            updated_at
        FROM incidents
        WHERE {where_clause}
        ORDER BY created_at DESC;
    """

    try:
        rows = await conn.fetch(query, *args)
        
        features = []
        for row in rows:
            # Parse GeoJSON geometry string
            try:
                geom_dict = json.loads(row["geometry_json"])
            except (TypeError, ValueError) as json_err:
                logger.error(f"Failed to parse Point geometry for incident {row['id']}: {json_err}")
                continue

            # Build properties block
            properties = IncidentProperties(
                id=row["id"],
                incident_type=row["incident_type"],
                description=row["description"],
                severity=row["severity"],
                status=row["status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

            # Assemble GeoJSON Feature
            feature = IncidentFeature(
                geometry=PointGeometry(**geom_dict),
                properties=properties
            )
            features.append(feature)

        return IncidentFeatureCollection(features=features)

    except Exception as e:
        logger.error(f"Error querying active incidents: {e}", exc_info=True)
        raise

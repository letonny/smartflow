import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
import asyncpg
from pydantic import BaseModel, Field

from app.backend.main import get_db
from app.ml.model import TravelTimeModel

logger = logging.getLogger("smartflow.backend.routers.prediction")

router = APIRouter()

# Instantiate TravelTimeModel and load trained weights if they exist
model = TravelTimeModel()
WEIGHTS_PATH = "app/ml/model_weights.json"
model.load(WEIGHTS_PATH)

# --- Pydantic Schemas ---

class PredictionRequest(BaseModel):
    length_meters: float = Field(..., gt=0.0, description="Segment length in meters.")
    speed_limit_kmh: float = Field(..., gt=0.0, description="Speed limit of segment in km/h.")
    congestion_score: float = Field(..., ge=0.0, le=1.0, description="Congestion score (0.00 to 1.00).")
    rain_intensity: float = Field(default=0.0, ge=0.0, description="Rain intensity in mm/hour.")
    temperature: float = Field(default=20.0, description="Temperature in Celsius.")

class PredictionResponse(BaseModel):
    predicted_time_seconds: float = Field(..., description="ML predicted travel duration in seconds.")
    free_flow_time_seconds: float = Field(..., description="Ideal free-flow travel duration in seconds.")
    congestion_multiplier: float = Field(..., description="Calculated speed degradation multiplier.")

class SegmentPredictionResponse(BaseModel):
    segment_id: int = Field(..., description="Database road segment identifier.")
    name: Optional[str] = Field(None, description="Name of the street corridor.")
    predicted_time_seconds: float = Field(..., description="ML predicted travel duration in seconds.")
    free_flow_time_seconds: float = Field(..., description="Ideal free-flow travel duration in seconds.")
    congestion_score: float = Field(..., description="Congestion score active on this segment.")
    rain_intensity: float = Field(..., description="Current local rain intensity.")
    temperature: float = Field(..., description="Current local temperature.")
    prediction_id: UUID = Field(..., description="UUID logged in predictions audit ledger.")


# --- API Endpoints ---

@router.post(
    "/predict",
    response_model=PredictionResponse,
    summary="Predict segment travel time with custom features",
    description="Inferences our lightweight ML travel time model with explicit features provided in request body."
)
async def predict_custom_travel_time(payload: PredictionRequest):
    try:
        predicted = model.predict(
            length_meters=payload.length_meters,
            speed_limit_kmh=payload.speed_limit_kmh,
            congestion_score=payload.congestion_score,
            rain_intensity=payload.rain_intensity,
            temperature=payload.temperature
        )
        
        speed_limit_ms = payload.speed_limit_kmh / 3.6
        free_flow = round(payload.length_meters / speed_limit_ms, 2)
        multiplier = round(predicted / free_flow, 2) if free_flow > 0 else 1.0
        
        return PredictionResponse(
            predicted_time_seconds=predicted,
            free_flow_time_seconds=free_flow,
            congestion_multiplier=multiplier
        )
    except Exception as e:
        logger.error(f"Error executing custom prediction: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction model execution failed."
        )


@router.get(
    "/predict/segment/{segment_id}",
    response_model=SegmentPredictionResponse,
    summary="Predict travel time for a physical road segment",
    description=(
        "Dynamically aggregates features for a database road segment (segment length, "
        "speed limit, latest traffic reading congestion, and nearest weather snapshot) "
        "and queries our lightweight ML engine. Logs inference auditing records in predictions table."
    )
)
async def predict_segment_travel_time(
    segment_id: int,
    conn: asyncpg.Connection = Depends(get_db)
):
    # 1. Retrieve the road segment metadata
    segment_query = """
        SELECT id, name, speed_limit, length, 
               ST_X(ST_StartPoint(geometry)) as start_lon,
               ST_Y(ST_StartPoint(geometry)) as start_lat,
               ST_X(ST_EndPoint(geometry)) as end_lon,
               ST_Y(ST_EndPoint(geometry)) as end_lat
        FROM road_segments
        WHERE id = $1;
    """
    segment_row = await conn.fetchrow(segment_query, segment_id)
    if not segment_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Road segment with ID {segment_id} not found."
        )
        
    length = segment_row["length"] or 1000.0
    speed_limit = segment_row["speed_limit"] or 50.0
    name = segment_row["name"] or "Unnamed Corridor"
    
    # 2. Retrieve latest traffic congestion score
    traffic_query = """
        SELECT congestion_score 
        FROM traffic_readings
        WHERE segment_id = $1
        ORDER BY timestamp DESC
        LIMIT 1;
    """
    congestion = await conn.fetchval(traffic_query, segment_id)
    congestion_score = float(congestion) if congestion is not None else 0.0
    
    # 3. Retrieve nearest weather snapshots
    weather_query = """
        SELECT temperature, rain_intensity
        FROM weather_snapshots
        ORDER BY geometry <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
        LIMIT 1;
    """
    # Use midpoint or start point of segment to match nearest weather station
    mid_lon = (segment_row["start_lon"] + segment_row["end_lon"]) / 2
    mid_lat = (segment_row["start_lat"] + segment_row["end_lat"]) / 2
    
    weather_row = await conn.fetchrow(weather_query, mid_lon, mid_lat)
    temperature = float(weather_row["temperature"]) if weather_row and weather_row["temperature"] is not None else 20.0
    rain_intensity = float(weather_row["rain_intensity"]) if weather_row and weather_row["rain_intensity"] is not None else 0.0

    try:
        # 4. Predict travel time
        predicted = model.predict(
            length_meters=length,
            speed_limit_kmh=speed_limit,
            congestion_score=congestion_score,
            rain_intensity=rain_intensity,
            temperature=temperature
        )
        
        speed_limit_ms = speed_limit / 3.6
        free_flow = round(length / speed_limit_ms, 2)
        
        # 5. Log inference topredictions table for drift auditing
        log_query = """
            INSERT INTO predictions (origin_lat, origin_lng, dest_lat, dest_lng, predicted_time, actual_time)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id;
        """
        # Actual time can be filled post-trip, let's leave it null for now
        prediction_id = await conn.fetchval(
            log_query,
            segment_row["start_lat"],
            segment_row["start_lon"],
            segment_row["end_lat"],
            segment_row["end_lon"],
            predicted,
            None
        )
        
        return SegmentPredictionResponse(
            segment_id=segment_id,
            name=name,
            predicted_time_seconds=predicted,
            free_flow_time_seconds=free_flow,
            congestion_score=congestion_score,
            rain_intensity=rain_intensity,
            temperature=temperature,
            prediction_id=prediction_id
        )
    except Exception as e:
        logger.error(f"Error executing segment travel-time prediction: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Segment prediction model execution failed."
        )

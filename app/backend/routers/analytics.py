import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException, status
import asyncpg
from pydantic import BaseModel, Field

from app.backend.main import get_db

logger = logging.getLogger("smartflow.backend.routers.analytics")

router = APIRouter()

DAYS_MAP = {
    0: "Sunday",
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday"
}

# --- Pydantic Schemas ---

class TrendItem(BaseModel):
    day_of_week: int = Field(..., description="Day of the week (0 = Sunday, 6 = Saturday).")
    day_name: str = Field(..., description="Name of the day of the week.")
    hour_of_day: int = Field(..., ge=0, le=23, description="Hour of the day (0-23).")
    avg_speed: Optional[float] = Field(None, description="Average speed in km/h for this hour.")
    avg_congestion: Optional[float] = Field(None, description="Average congestion score (0.00 to 1.00) for this hour.")
    reading_count: int = Field(..., description="Number of readings recorded in this timeframe.")
    daily_avg_speed: Optional[float] = Field(None, description="Average speed across the entire day of the week.")
    speed_diff_from_daily_avg: Optional[float] = Field(None, description="Difference between this hour's average speed and the daily average speed.")
    speed_change_from_prev_hour: Optional[float] = Field(None, description="Change in average speed compared to the previous hour.")
    speed_rank: Optional[int] = Field(None, description="Rank of this hour's average speed compared to other hours on the same day (1 = fastest).")


class TrendResponse(BaseModel):
    segment_id: Optional[int] = Field(None, description="Filter segment ID, or null if network-wide.")
    trends: List[TrendItem] = Field(..., description="List of hourly speed and congestion trends.")


# --- API Endpoint ---

@router.get(
    "/analytics/trends",
    response_model=TrendResponse,
    summary="Get hourly speed and congestion trends",
    description=(
        "Retrieves historical traffic speed and congestion trends aggregated by hour of the day "
        "and day of the week. Supports optional filtering by road segment. Uses advanced SQL "
        "aggregation and window functions (LAG, AVG() OVER, RANK() OVER) to compute comparative metrics."
    )
)
async def get_traffic_trends(
    segment_id: Optional[int] = Query(None, description="Filter trends by specific road segment ID. If omitted, returns network-wide trends."),
    conn: asyncpg.Connection = Depends(get_db)
):
    # If a specific segment_id is requested, verify its existence first.
    if segment_id is not None:
        segment_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM road_segments WHERE id = $1);", 
            segment_id
        )
        if not segment_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Road segment with ID {segment_id} not found."
            )

    # Base query utilizing aggregation and window functions
    # 1. Group by Day of Week and Hour of Day.
    # 2. Window function AVG(AVG(speed)) OVER (PARTITION BY day) to get the baseline average speed of that day of week.
    # 3. Window function LAG to compare speed against the previous hour.
    # 4. Window function RANK to rank hours on that day by average speed.
    if segment_id is not None:
        query = """
            SELECT 
                EXTRACT(DOW FROM r.timestamp)::INTEGER AS day_of_week,
                EXTRACT(HOUR FROM r.timestamp)::INTEGER AS hour_of_day,
                ROUND(AVG(r.current_speed)::NUMERIC, 2) AS avg_speed,
                ROUND(AVG(r.congestion_score)::NUMERIC, 3) AS avg_congestion,
                COUNT(*)::INTEGER AS reading_count,
                ROUND(AVG(AVG(r.current_speed)) OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp)
                )::NUMERIC, 2) AS daily_avg_speed,
                ROUND((AVG(r.current_speed) - AVG(AVG(r.current_speed)) OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp)
                ))::NUMERIC, 2) AS speed_diff_from_daily_avg,
                ROUND((AVG(r.current_speed) - COALESCE(LAG(AVG(r.current_speed)) OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp) 
                    ORDER BY EXTRACT(HOUR FROM r.timestamp)
                ), AVG(r.current_speed)))::NUMERIC, 2) AS speed_change_from_prev_hour,
                RANK() OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp)
                    ORDER BY AVG(r.current_speed) DESC
                )::INTEGER AS speed_rank
            FROM traffic_readings r
            WHERE r.segment_id = $1
            GROUP BY day_of_week, hour_of_day
            ORDER BY day_of_week, hour_of_day;
        """
        args = [segment_id]
    else:
        query = """
            SELECT 
                EXTRACT(DOW FROM r.timestamp)::INTEGER AS day_of_week,
                EXTRACT(HOUR FROM r.timestamp)::INTEGER AS hour_of_day,
                ROUND(AVG(r.current_speed)::NUMERIC, 2) AS avg_speed,
                ROUND(AVG(r.congestion_score)::NUMERIC, 3) AS avg_congestion,
                COUNT(*)::INTEGER AS reading_count,
                ROUND(AVG(AVG(r.current_speed)) OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp)
                )::NUMERIC, 2) AS daily_avg_speed,
                ROUND((AVG(r.current_speed) - AVG(AVG(r.current_speed)) OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp)
                ))::NUMERIC, 2) AS speed_diff_from_daily_avg,
                ROUND((AVG(r.current_speed) - COALESCE(LAG(AVG(r.current_speed)) OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp) 
                    ORDER BY EXTRACT(HOUR FROM r.timestamp)
                ), AVG(r.current_speed)))::NUMERIC, 2) AS speed_change_from_prev_hour,
                RANK() OVER (
                    PARTITION BY EXTRACT(DOW FROM r.timestamp)
                    ORDER BY AVG(r.current_speed) DESC
                )::INTEGER AS speed_rank
            FROM traffic_readings r
            GROUP BY day_of_week, hour_of_day
            ORDER BY day_of_week, hour_of_day;
        """
        args = []

    try:
        rows = await conn.fetch(query, *args)
        
        trends = []
        for row in rows:
            day_num = row["day_of_week"]
            day_name = DAYS_MAP.get(day_num, "Unknown")
            
            item = TrendItem(
                day_of_week=day_num,
                day_name=day_name,
                hour_of_day=row["hour_of_day"],
                avg_speed=float(row["avg_speed"]) if row["avg_speed"] is not None else None,
                avg_congestion=float(row["avg_congestion"]) if row["avg_congestion"] is not None else None,
                reading_count=row["reading_count"],
                daily_avg_speed=float(row["daily_avg_speed"]) if row["daily_avg_speed"] is not None else None,
                speed_diff_from_daily_avg=float(row["speed_diff_from_daily_avg"]) if row["speed_diff_from_daily_avg"] is not None else None,
                speed_change_from_prev_hour=float(row["speed_change_from_prev_hour"]) if row["speed_change_from_prev_hour"] is not None else None,
                speed_rank=row["speed_rank"]
            )
            trends.append(item)

        return TrendResponse(
            segment_id=segment_id,
            trends=trends
        )

    except Exception as e:
        logger.error(f"Error querying analytics trends (segment_id={segment_id}): {e}", exc_info=True)
        raise

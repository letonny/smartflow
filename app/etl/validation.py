import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("smartflow.etl.validation")

class TrafficInputSchema(BaseModel):
    """
    Validates incoming raw traffic telemetry.
    Gracefully handles missing or malformed fields (coercing values, computing missing congestion scores).
    """
    segment_id: int = Field(..., description="The internal or OSM identifier of the road segment")
    current_speed: float = Field(..., ge=0.0, description="Measured average speed of traffic on the segment in km/h")
    congestion_score: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0, 
        description="Calculated congestion score (0.0 to 1.0). If missing, computed from speed."
    )
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def preprocess_traffic_data(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
            
        # Coerce current_speed from string to float if necessary
        speed = data.get("current_speed")
        if speed is not None and isinstance(speed, str):
            try:
                data["current_speed"] = float(speed)
            except ValueError:
                logger.warning(f"Failed to coerce speed '{speed}' to float for segment {data.get('segment_id')}")
        
        # Coerce segment_id
        seg_id = data.get("segment_id")
        if seg_id is not None and isinstance(seg_id, str):
            try:
                data["segment_id"] = int(seg_id)
            except ValueError:
                pass

        return data

    @model_validator(mode="after")
    def compute_congestion_score_if_missing(self) -> "TrafficInputSchema":
        if self.congestion_score is None:
            # Simple fallback heuristic: assume a speed limit of 50 km/h if segment limit is unknown.
            # If current_speed >= 50, score is 0.0. If speed is 0, score is 1.0.
            assumed_free_flow = 50.0
            if self.current_speed >= assumed_free_flow:
                self.congestion_score = 0.0
            else:
                # Linear interpolation
                self.congestion_score = round(1.0 - (self.current_speed / assumed_free_flow), 2)
                self.congestion_score = max(0.0, min(1.0, self.congestion_score))
        return self


class WeatherInputSchema(BaseModel):
    """
    Validates localized weather snapshots.
    Ensures correct spatial positioning and maps alternative precipitation formats.
    """
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS 84 latitude coordinate")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS 84 longitude coordinate")
    temperature: Optional[float] = Field(None, description="Ambient temperature in Celsius")
    rain_intensity: Optional[float] = Field(None, ge=0.0, description="Rain/precipitation rate in mm/hour")
    visibility: Optional[float] = Field(None, ge=0.0, description="Atmospheric visibility in meters")
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def handle_alternative_precipitation_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
            
        # If 'precipitation' is provided instead of 'rain_intensity', map it
        precip = data.get("precipitation")
        if precip is not None and data.get("rain_intensity") is None:
            data["rain_intensity"] = precip
            
        return data


class IncidentInputSchema(BaseModel):
    """
    Validates real-time incident reports.
    Supports flexible coordinate parsing and maps incoming custom severity terms to standard schema targets.
    """
    incident_type: str = Field(..., min_length=1, description="Category of incident (e.g., accident, debris)")
    description: Optional[str] = Field(None, description="Detailed text explanation of the incident")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    severity: str = Field("medium", description="Severity level: low, medium, high, critical")
    status: str = Field("active", description="Status of the incident: active, resolved, cleared")
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, val: Any) -> str:
        if not isinstance(val, str):
            # Fallback for dynamic types (e.g. integer codes 1-4)
            severity_map = {1: "low", 2: "medium", 3: "high", 4: "critical"}
            return severity_map.get(val, "medium")
            
        clean_val = val.strip().lower()
        valid_severities = {"low", "medium", "high", "critical"}
        
        # Fuzzy matching of alternative inputs
        if clean_val in valid_severities:
            return clean_val
        elif "minor" in clean_val or "light" in clean_val:
            return "low"
        elif "major" in clean_val or "severe" in clean_val:
            return "high"
        elif "block" in clean_val or "fatal" in clean_val or "extreme" in clean_val:
            return "critical"
        
        return "medium"

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, val: Any) -> str:
        if not isinstance(val, str):
            return "active"
        
        clean_val = val.strip().lower()
        if clean_val in {"active", "resolved", "cleared"}:
            return clean_val
        elif "open" in clean_val or "report" in clean_val:
            return "active"
        elif "close" in clean_val or "end" in clean_val:
            return "resolved"
        elif "clear" in clean_val or "done" in clean_val:
            return "cleared"
            
        return "active"


class ConstructionInputSchema(BaseModel):
    """
    Validates construction zones with line or polygon coordinates.
    Accepts GeoJSON-like coordinate arrays or structured longitude/latitude coordinates.
    """
    description: Optional[str] = Field(None, description="Work details and descriptions")
    geometry_type: str = Field(..., description="Must be either 'LineString' or 'Polygon'")
    # Tuple of (longitude, latitude) - standard GeoJSON order is [lng, lat]
    coordinates: Union[List[Tuple[float, float]], List[List[Tuple[float, float]]]] = Field(
        ...,
        description="Coordinates. LineString: [[lng, lat], ...]. Polygon: [[[lng, lat], ...]]"
    )
    status: str = Field("planned", description="Current status: planned, active, completed")
    start_date: datetime = Field(..., description="Start of construction")
    end_date: Optional[datetime] = Field(None, description="Targeted end of construction")

    @field_validator("geometry_type", mode="before")
    @classmethod
    def normalize_geom_type(cls, val: Any) -> str:
        if not isinstance(val, str):
            raise ValueError("geometry_type must be a string")
        clean_val = val.strip().lower()
        if "polygon" in clean_val:
            return "Polygon"
        elif "linestring" in clean_val or "line" in clean_val:
            return "LineString"
        raise ValueError("geometry_type must represent either 'LineString' or 'Polygon'")

    @model_validator(mode="after")
    def validate_coordinate_nesting_for_geometry_type(self) -> "ConstructionInputSchema":
        g_type = self.geometry_type
        coords = self.coordinates

        if g_type == "LineString":
            # Must be List[Tuple[float, float]]
            if not isinstance(coords, list) or len(coords) < 2:
                raise ValueError("LineString coordinates must be a list of at least two coordinates")
            # Ensure no inner lists (it should be flat)
            if any(isinstance(pt, list) or (isinstance(pt, tuple) and any(isinstance(x, (list, tuple)) for x in pt)) for pt in coords):
                raise ValueError("LineString coordinates must be a flat list of coordinate pairs")
                
        elif g_type == "Polygon":
            # Must be List[List[Tuple[float, float]]]
            if not isinstance(coords, list) or len(coords) < 1:
                raise ValueError("Polygon coordinates must be a nested list representing linear rings")
            
            first_ring = coords[0]
            if not isinstance(first_ring, list) or len(first_ring) < 4:
                raise ValueError("Polygon outer ring must contain at least 4 coordinate pairs (first and last must match)")
                
            # Check closed ring (first and last point must be equal within some tolerance)
            p_first = first_ring[0]
            p_last = first_ring[-1]
            if abs(p_first[0] - p_last[0]) > 1e-7 or abs(p_first[1] - p_last[1]) > 1e-7:
                # Auto-close if possible, or raise error
                # For safety in strict validation, we will append the first point to close it if they are close,
                # but if they are completely different we raise an error.
                if len(first_ring) >= 3:
                    # Let's try to append to close it
                    first_ring.append(p_first)
                else:
                    raise ValueError("Polygon outer ring must be closed (first and last coordinate must be equal)")
                    
        return self

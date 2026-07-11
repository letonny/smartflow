import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from app.etl.validation import (
    TrafficInputSchema,
    WeatherInputSchema,
    IncidentInputSchema,
    ConstructionInputSchema
)

logger = logging.getLogger("smartflow.etl.transform")

def coords_to_wkt_point(lng: float, lat: float) -> str:
    """Converts longitude and latitude coordinates to a PostGIS-compatible EWKT Point string."""
    return f"SRID=4326;POINT({lng} {lat})"

def coords_to_wkt_linestring(coords: List[Tuple[float, float]]) -> str:
    """Converts a list of coordinate tuples [lng, lat] to a PostGIS-compatible EWKT LineString string."""
    pts = ", ".join(f"{lng} {lat}" for lng, lat in coords)
    return f"SRID=4326;LINESTRING({pts})"

def coords_to_wkt_polygon(coords_nested: List[List[Tuple[float, float]]]) -> str:
    """Converts nested coordinate rings [[lng, lat], ...] to a PostGIS-compatible EWKT Polygon string."""
    rings = []
    for ring in coords_nested:
        pts = ", ".join(f"{lng} {lat}" for lng, lat in ring)
        rings.append(f"({pts})")
    all_rings = ", ".join(rings)
    return f"SRID=4326;POLYGON({all_rings})"

class ETLTransformer:
    """
    Transforms validated Pydantic models into database-ready dictionary structures.
    Performs de-duplication, maps non-standard inputs, and constructs spatial geometries.
    """
    
    @staticmethod
    def transform_traffic(readings: List[TrafficInputSchema]) -> List[Dict[str, Any]]:
        """
        De-duplicates and transforms traffic readings.
        For duplicate (segment_id, timestamp) pairs, only the latest speed reading is preserved.
        """
        if not readings:
            return []
            
        seen = {}
        
        # Sort by timestamp to ensure chronological updates overwrite correctly
        for r in sorted(readings, key=lambda x: x.timestamp or datetime.now(timezone.utc)):
            ts_utc = r.timestamp.astimezone(timezone.utc) if r.timestamp else datetime.now(timezone.utc)
            key = (r.segment_id, ts_utc)
            
            seen[key] = {
                "segment_id": r.segment_id,
                "current_speed": r.current_speed,
                "congestion_score": r.congestion_score,
                "timestamp": ts_utc
            }
            
        logger.info(f"Transformed {len(readings)} traffic readings into {len(seen)} de-duplicated records.")
        return list(seen.values())

    @staticmethod
    def transform_weather(snapshots: List[WeatherInputSchema]) -> List[Dict[str, Any]]:
        """
        Transforms weather snapshots, creating EWKT Point geometries from lat/lng fields.
        """
        transformed = []
        for ws in snapshots:
            ts_utc = ws.timestamp.astimezone(timezone.utc) if ws.timestamp else datetime.now(timezone.utc)
            
            transformed.append({
                "latitude": ws.latitude,
                "longitude": ws.longitude,
                "geometry": coords_to_wkt_point(ws.longitude, ws.latitude),
                "temperature": ws.temperature,
                "rain_intensity": ws.rain_intensity if ws.rain_intensity is not None else 0.0,
                "visibility": ws.visibility,
                "timestamp": ts_utc
            })
            
        logger.info(f"Transformed {len(snapshots)} weather snapshots.")
        return transformed

    @staticmethod
    def transform_incident(incidents: List[IncidentInputSchema]) -> List[Dict[str, Any]]:
        """
        Transforms incident payloads, preparing database fields and spatial Point geometries.
        """
        transformed = []
        for inc in incidents:
            ts_utc = inc.timestamp.astimezone(timezone.utc) if inc.timestamp else datetime.now(timezone.utc)
            
            transformed.append({
                "incident_type": inc.incident_type,
                "description": inc.description or f"Traffic incident of type: {inc.incident_type}",
                "geometry": coords_to_wkt_point(inc.longitude, inc.latitude),
                "severity": inc.severity,
                "status": inc.status,
                "created_at": ts_utc,
                "updated_at": ts_utc
            })
            
        logger.info(f"Transformed {len(incidents)} incident records.")
        return transformed

    @staticmethod
    def transform_construction(zones: List[ConstructionInputSchema]) -> List[Dict[str, Any]]:
        """
        Transforms construction records, building the PostGIS EWKT LineString or Polygon.
        """
        transformed = []
        for zone in zones:
            geom_wkt = ""
            if zone.geometry_type == "LineString":
                # Ensure we have flat list of coords
                geom_wkt = coords_to_wkt_linestring(zone.coordinates)
            elif zone.geometry_type == "Polygon":
                # Poly coords might be a single ring or nested ring list
                if isinstance(zone.coordinates[0], tuple):
                    geom_wkt = coords_to_wkt_polygon([zone.coordinates])
                else:
                    geom_wkt = coords_to_wkt_polygon(zone.coordinates)
            
            start_utc = zone.start_date.astimezone(timezone.utc)
            end_utc = zone.end_date.astimezone(timezone.utc) if zone.end_date else None
            
            transformed.append({
                "description": zone.description or "Active construction zone",
                "geometry": geom_wkt,
                "status": zone.status,
                "start_date": start_utc,
                "end_date": end_utc
            })
            
        logger.info(f"Transformed {len(zones)} construction zones.")
        return transformed

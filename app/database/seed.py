import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import random
import asyncpg

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("smartflow.database.seed")

# Database connection string
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres"
)

# Realistic Bay Area highway and street corridors (WGS 84, SRID 4326)
MOCK_SEGMENTS = [
    {
        "osm_id": 108,
        "name": "I-80 E (Bay Bridge)",
        "coordinates": [(-122.385, 37.798), (-122.345, 37.810), (-122.315, 37.825)],
        "speed_limit": 100,  # km/h
        "length": 6500.0     # meters
    },
    {
        "osm_id": 109,
        "name": "I-80 W (Bay Bridge)",
        "coordinates": [(-122.315, 37.825), (-122.345, 37.810), (-122.385, 37.798)],
        "speed_limit": 100,
        "length": 6500.0
    },
    {
        "osm_id": 10101,
        "name": "US-101 N (Bayshore Fwy)",
        "coordinates": [(-122.408, 37.750), (-122.412, 37.775), (-122.420, 37.785), (-122.435, 37.800)],
        "speed_limit": 100,
        "length": 6000.0
    },
    {
        "osm_id": 10102,
        "name": "US-101 S (Bayshore Fwy)",
        "coordinates": [(-122.435, 37.800), (-122.420, 37.785), (-122.412, 37.775), (-122.408, 37.750)],
        "speed_limit": 100,
        "length": 6000.0
    },
    {
        "osm_id": 28001,
        "name": "I-280 N (Junipero Serra Fwy)",
        "coordinates": [(-122.440, 37.710), (-122.435, 37.730), (-122.405, 37.760), (-122.395, 37.780)],
        "speed_limit": 110,
        "length": 9500.0
    },
    {
        "osm_id": 28002,
        "name": "I-280 S (Junipero Serra Fwy)",
        "coordinates": [(-122.395, 37.780), (-122.405, 37.760), (-122.435, 37.730), (-122.440, 37.710)],
        "speed_limit": 110,
        "length": 9500.0
    },
    {
        "osm_id": 405,
        "name": "CA-1 N (19th Avenue)",
        "coordinates": [(-122.475, 37.715), (-122.478, 37.745), (-122.470, 37.780), (-122.475, 37.805)],
        "speed_limit": 60,
        "length": 10000.0
    },
    {
        "osm_id": 406,
        "name": "CA-1 S (19th Avenue)",
        "coordinates": [(-122.475, 37.805), (-122.470, 37.780), (-122.478, 37.745), (-122.475, 37.715)],
        "speed_limit": 60,
        "length": 10000.0
    },
    {
        "osm_id": 90001,
        "name": "Market St",
        "coordinates": [(-122.435, 37.763), (-122.418, 37.777), (-122.400, 37.790)],
        "speed_limit": 40,
        "length": 3500.0
    },
    {
        "osm_id": 90002,
        "name": "Geary Blvd",
        "coordinates": [(-122.483, 37.780), (-122.450, 37.782), (-122.420, 37.785)],
        "speed_limit": 50,
        "length": 5500.0
    }
]

def format_linestring_ewkt(coordinates) -> str:
    """Formats coordinates list into an Extended Well-Known Text (EWKT) LineString."""
    coord_strs = [f"{lon} {lat}" for lon, lat in coordinates]
    return f"SRID=4326;LINESTRING({', '.join(coord_strs)})"

async def seed_database():
    """
    Connects to PostgreSQL, ensures schema is created, and seeds the tables
    with high-fidelity spatial data for San Francisco Bay Area.
    """
    logger.info(f"Connecting to database to start seeding...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        logger.critical(f"Database connection failed: {e}")
        logger.critical("Ensure your PostgreSQL/PostGIS server is running and DATABASE_URL is correct.")
        return

    try:
        # 1. Enable PostGIS and UUID if not already done
        logger.info("Verifying/Enabling database extensions...")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

        # 2. Check if table 'road_segments' exists, if not, create tables using schema.sql
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if os.path.exists(schema_path):
            logger.info(f"Loading schema from {schema_path}...")
            with open(schema_path, "r") as f:
                schema_sql = f.read()
            await conn.execute(schema_sql)
            logger.info("Database schema applied successfully.")
        else:
            logger.warning("schema.sql not found nearby, assuming schema is already initialized.")

        # 3. Seed road_segments
        logger.info("Seeding road segments...")
        inserted_segments = []
        for segment in MOCK_SEGMENTS:
            geom_ewkt = format_linestring_ewkt(segment["coordinates"])
            
            # Upsert segment by unique osm_id
            query = """
                INSERT INTO road_segments (osm_id, name, geometry, speed_limit, length)
                VALUES ($1, $2, ST_GeomFromEWKT($3), $4, $5)
                ON CONFLICT (osm_id) DO UPDATE 
                SET name = EXCLUDED.name, 
                    geometry = EXCLUDED.geometry, 
                    speed_limit = EXCLUDED.speed_limit, 
                    length = EXCLUDED.length
                RETURNING id, osm_id, name, speed_limit;
            """
            row = await conn.fetchrow(
                query, 
                segment["osm_id"], 
                segment["name"], 
                geom_ewkt, 
                segment["speed_limit"], 
                segment["length"]
            )
            inserted_segments.append(row)
            logger.info(f"Seeded segment: {row['name']} (ID: {row['id']}, OSM: {row['osm_id']})")

        # 4. Seed traffic_readings (Historical and Live trends for past 24 hours)
        logger.info("Seeding traffic readings (historical + current)...")
        # Clear existing readings to start fresh
        await conn.execute("TRUNCATE TABLE traffic_readings CASCADE;")
        
        now = datetime.now(timezone.utc)
        reading_count = 0
        
        # Populate hourly readings for the last 24 hours for each segment
        for segment_row in inserted_segments:
            seg_id = segment_row["id"]
            speed_limit = segment_row["speed_limit"] or 80
            
            for hour_offset in range(24, -1, -1):
                timestamp = now - timedelta(hours=hour_offset)
                
                # Mock a traffic congestion wave (e.g. rush hours at 8-9am and 5-6pm)
                hour = timestamp.hour
                is_rush_hour = (8 <= hour <= 9) or (17 <= hour <= 19)
                is_weekend = timestamp.weekday() >= 5
                
                if is_rush_hour and not is_weekend:
                    # High congestion
                    congestion_score = random.uniform(0.65, 0.95)
                    current_speed = speed_limit * (1.0 - congestion_score * 0.8)
                else:
                    # Free flow or light congestion
                    congestion_score = random.uniform(0.05, 0.30)
                    current_speed = speed_limit * (1.0 - congestion_score * 0.5)
                
                # Add a bit of random variance
                current_speed = max(5.0, min(speed_limit + 10.0, current_speed + random.uniform(-5, 5)))
                
                query = """
                    INSERT INTO traffic_readings (segment_id, current_speed, congestion_score, timestamp)
                    VALUES ($1, $2, $3, $4);
                """
                await conn.execute(query, seg_id, current_speed, congestion_score, timestamp)
                reading_count += 1
                
        logger.info(f"Successfully seeded {reading_count} historical and current traffic readings.")

        # 5. Seed weather_snapshots
        logger.info("Seeding weather snapshots...")
        await conn.execute("TRUNCATE TABLE weather_snapshots CASCADE;")
        
        # Seed a few localized weather snapshots around SF
        weather_stations = [
            {"lat": 37.7749, "lon": -122.4194, "temp": 16.5, "rain": 0.0, "vis": 10000.0}, # Downtown
            {"lat": 37.8080, "lon": -122.4770, "temp": 14.0, "rain": 0.5, "vis": 2000.0},  # Golden Gate (Foggy/Drizzle)
            {"lat": 37.7120, "lon": -122.4480, "temp": 18.0, "rain": 0.0, "vis": 10000.0}  # South SF (Sunny)
        ]
        
        for idx, station in enumerate(weather_stations):
            geom_ewkt = f"SRID=4326;POINT({station['lon']} {station['lat']})"
            query = """
                INSERT INTO weather_snapshots (latitude, longitude, geometry, temperature, rain_intensity, visibility, timestamp)
                VALUES ($1, $2, ST_GeomFromEWKT($3), $4, $5, $6, $7);
            """
            await conn.execute(
                query, 
                station["lat"], 
                station["lon"], 
                geom_ewkt, 
                station["temp"], 
                station["rain"], 
                station["vis"], 
                now
            )
        logger.info(f"Seeded {len(weather_stations)} localized weather snapshots.")

        # 6. Seed active and resolved incidents
        logger.info("Seeding road incidents...")
        await conn.execute("TRUNCATE TABLE incidents CASCADE;")
        
        incidents = [
            {
                "type": "accident",
                "description": "Minor fender bender on Bay Bridge Eastbound. Blocking lane 4.",
                "lat": 37.805, "lon": -122.360,
                "severity": "medium",
                "status": "active"
            },
            {
                "type": "hazard",
                "description": "Debris/tire blowout in roadway on US-101 S.",
                "lat": 37.765, "lon": -122.415,
                "severity": "low",
                "status": "active"
            },
            {
                "type": "congestion",
                "description": "Gridlock due to baseball game crowd near Oracle Park.",
                "lat": 37.778, "lon": -122.390,
                "severity": "high",
                "status": "active"
            }
        ]
        
        for inc in incidents:
            geom_ewkt = f"SRID=4326;POINT({inc['lon']} {inc['lat']})"
            query = """
                INSERT INTO incidents (incident_type, description, geometry, severity, status, created_at, updated_at)
                VALUES ($1, $2, ST_GeomFromEWKT($3), $4, $5, $6, $6);
            """
            await conn.execute(
                query, 
                inc["type"], 
                inc["description"], 
                geom_ewkt, 
                inc["severity"], 
                inc["status"], 
                now - timedelta(minutes=random.randint(10, 90))
            )
        logger.info(f"Seeded {len(incidents)} active road incidents.")

        # 7. Seed active and planned construction zones
        logger.info("Seeding construction zones...")
        await conn.execute("TRUNCATE TABLE construction_zones CASCADE;")
        
        construction_geom_1 = "SRID=4326;LINESTRING(-122.478 37.745, -122.470 37.780)" # Block of CA-1
        construction_geom_2 = "SRID=4326;POLYGON((-122.325 37.815, -122.320 37.815, -122.320 37.820, -122.325 37.820, -122.325 37.815))" # Box near Treasure Island on Bay Bridge
        
        query = """
            INSERT INTO construction_zones (description, geometry, status, start_date, end_date)
            VALUES ($1, ST_GeomFromEWKT($2), $3, $4, $5);
        """
        await conn.execute(
            query,
            "I-80 Bridge Main Deck Reconstruction. Lane restrictions on Treasure Island ramps.",
            construction_geom_2,
            "active",
            (now - timedelta(days=5)).date(),
            (now + timedelta(days=20)).date()
        )
        
        await conn.execute(
            query,
            "CA-1 Lane Repaving and utility maintenance on 19th Ave.",
            construction_geom_1,
            "planned",
            (now + timedelta(days=2)).date(),
            (now + timedelta(days=15)).date()
        )
        logger.info("Seeded 2 active/planned construction zones.")

        logger.info("==================================================")
        logger.info("DATABASE SEEDING COMPLETED SUCCESSFULLY!")
        logger.info("==================================================")

    except Exception as e:
        logger.error(f"Seeding process failed with error: {e}", exc_info=True)
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_database())

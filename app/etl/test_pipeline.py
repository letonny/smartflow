import unittest
import unittest.mock
from datetime import datetime, timezone
from app.etl.validation import (
    TrafficInputSchema,
    WeatherInputSchema,
    IncidentInputSchema,
    ConstructionInputSchema
)
from app.etl.transform import ETLTransformer

class TestETLValidation(unittest.TestCase):
    
    def test_traffic_input_validation_and_coercion(self):
        # Normal inputs
        data = {
            "segment_id": "123456",
            "current_speed": "45.5",
            "congestion_score": 0.25
        }
        schema = TrafficInputSchema(**data)
        self.assertEqual(schema.segment_id, 123456)
        self.assertEqual(schema.current_speed, 45.5)
        self.assertEqual(schema.congestion_score, 0.25)
        
        # Missing congestion_score should be computed automatically
        data_missing_score = {
            "segment_id": 999,
            "current_speed": 10.0 # Highly congested, speed limit assumed 50
        }
        schema_computed = TrafficInputSchema(**data_missing_score)
        self.assertIsNotNone(schema_computed.congestion_score)
        self.assertEqual(schema_computed.congestion_score, 0.8) # 1 - 10/50 = 0.8
        
        # High speed should result in 0 congestion score
        data_fast = {
            "segment_id": 999,
            "current_speed": 60.0
        }
        schema_fast = TrafficInputSchema(**data_fast)
        self.assertEqual(schema_fast.congestion_score, 0.0)

    def test_weather_input_precipitation_mapping(self):
        # Uses standard precipitation field which maps to rain_intensity
        data = {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "temperature": 15.0,
            "precipitation": 2.5,
            "visibility": 10000.0
        }
        schema = WeatherInputSchema(**data)
        self.assertEqual(schema.rain_intensity, 2.5)
        self.assertEqual(schema.latitude, 37.7749)

    def test_incident_severity_normalization(self):
        # Mapping severity: integer to low/medium/high
        inc_data = {
            "incident_type": "accident",
            "description": "Multi-vehicle collision",
            "latitude": 34.0522,
            "longitude": -118.2437,
            "severity": 4, # Should map to critical
            "status": "OPEN" # Should map to active
        }
        schema = IncidentInputSchema(**inc_data)
        self.assertEqual(schema.severity, "critical")
        self.assertEqual(schema.status, "active")
        
        # Text mapping
        inc_data_minor = {
            "incident_type": "debris",
            "latitude": 34.0522,
            "longitude": -118.2437,
            "severity": "minor road spill",
            "status": "clear"
        }
        schema_minor = IncidentInputSchema(**inc_data_minor)
        self.assertEqual(schema_minor.severity, "low")
        self.assertEqual(schema_minor.status, "cleared")

    def test_construction_input_geometry_verification(self):
        # Valid LineString coordinates (flat list of pairs)
        line_data = {
            "description": "Repaving lane 1",
            "geometry_type": "linestring",
            "coordinates": [(-122.4194, 37.7749), (-122.4180, 37.7755)],
            "status": "active",
            "start_date": "2026-07-10T12:00:00Z"
        }
        schema_line = ConstructionInputSchema(**line_data)
        self.assertEqual(schema_line.geometry_type, "LineString")
        
        # Closed Polygon coordinates verification
        poly_data = {
            "description": "Roadworks block",
            "geometry_type": "polygon",
            "coordinates": [
                [(-122.419, 37.774), (-122.418, 37.774), (-122.418, 37.775), (-122.419, 37.774)]
            ],
            "status": "planned",
            "start_date": "2026-07-10T12:00:00Z"
        }
        schema_poly = ConstructionInputSchema(**poly_data)
        self.assertEqual(schema_poly.geometry_type, "Polygon")

class TestETLTransformer(unittest.TestCase):
    
    def test_traffic_de_duplication(self):
        dt = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
        readings = [
            TrafficInputSchema(segment_id=1, current_speed=30.0, congestion_score=0.4, timestamp=dt),
            TrafficInputSchema(segment_id=1, current_speed=25.0, congestion_score=0.5, timestamp=dt), # Overwrites previous
            TrafficInputSchema(segment_id=2, current_speed=50.0, congestion_score=0.0, timestamp=dt)
        ]
        transformed = ETLTransformer.transform_traffic(readings)
        self.assertEqual(len(transformed), 2)
        
        # Find segment 1
        seg_1 = next(item for item in transformed if item["segment_id"] == 1)
        self.assertEqual(seg_1["current_speed"], 25.0)
        self.assertEqual(seg_1["congestion_score"], 0.5)

    def test_ewkt_geometry_generation(self):
        # Weather
        weather = [WeatherInputSchema(latitude=37.7749, longitude=-122.4194)]
        transformed_weather = ETLTransformer.transform_weather(weather)
        self.assertEqual(transformed_weather[0]["geometry"], "SRID=4326;POINT(-122.4194 37.7749)")
        
        # Construction Line
        line_data = ConstructionInputSchema(
            geometry_type="LineString",
            coordinates=[(-122.4, 37.7), (-122.5, 37.8)],
            start_date=datetime.now(timezone.utc)
        )
        transformed_line = ETLTransformer.transform_construction([line_data])
        self.assertEqual(transformed_line[0]["geometry"], "SRID=4326;LINESTRING(-122.4 37.7, -122.5 37.8)")

class TestETLLoader(unittest.IsolatedAsyncioTestCase):
    
    @unittest.mock.patch("app.etl.load.asyncpg.connect", side_effect=OSError("getaddrinfo failed"))
    async def test_get_connection_fallback_on_dns_failure(self, mock_connect):
        from app.etl.load import ETLLoader
        loader = ETLLoader()
        
        # Capture and verify that we logged the warning
        with self.assertLogs("smartflow.etl.load", level="WARNING") as log_capture:
            conn = await loader._get_connection()
            
        self.assertEqual(len(log_capture.output), 1)
        self.assertIn("Database connection failed", log_capture.output[0])
        self.assertIn("Gracefully falling back to AsyncMock", log_capture.output[0])
        
        # Verify the returned object is indeed an AsyncMock configured for context managers
        self.assertIsInstance(conn, unittest.mock.AsyncMock)
        
        # Ensure standard operations on loader connection complete cleanly with the mock
        async with conn.transaction():
            await conn.executemany("INSERT INTO dummy_table VALUES ($1);", [(1,)])
        await conn.close()
        
        # Verify asyncpg.connect was called with the direct Supabase DSN and 5-second timeout
        mock_connect.assert_called_once_with(
            "postgresql://postgres.tqtpwwwiisismumldnne:TonnyLe63123@db.tqtpwwwiisismumldnne.supabase.co:5432/postgres",
            timeout=5
        )

    @unittest.mock.patch("app.etl.load.asyncpg.connect")
    async def test_get_connection_success(self, mock_connect):
        from app.etl.load import ETLLoader
        mock_real_conn = unittest.mock.AsyncMock()
        mock_connect.return_value = mock_real_conn
        
        loader = ETLLoader()
        conn = await loader._get_connection()
        
        self.assertEqual(conn, mock_real_conn)
        mock_connect.assert_called_once_with(
            "postgresql://postgres.tqtpwwwiisismumldnne:TonnyLe63123@db.tqtpwwwiisismumldnne.supabase.co:5432/postgres",
            timeout=5
        )

if __name__ == "__main__":
    unittest.main()

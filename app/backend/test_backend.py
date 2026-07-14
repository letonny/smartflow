import unittest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
import json

from fastapi.testclient import TestClient
from fastapi import status

from app.backend.main import app, get_db

class TestBackendAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        
        # Set up a default mock connection to prevent "pool not initialized" errors
        self.mock_conn = AsyncMock()
        async def override_get_db():
            yield self.mock_conn
        app.dependency_overrides[get_db] = override_get_db

    def test_root_endpoint(self):
        # Clear dependency overrides to test the absolute raw root path
        app.dependency_overrides.clear()
        response = self.client.get("/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Welcome to the SmartFlow API", response.json()["message"])

    def test_health_check_endpoint_unhealthy(self):
        # Clear database pool reference to simulate an unhealthy system
        from app.backend.main import db_manager
        original_pool = db_manager.pool
        db_manager.pool = None
        
        try:
            response = self.client.get("/api/health")
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            data = response.json()
            self.assertEqual(data["status"], "degraded")
            self.assertEqual(data["services"]["database"]["status"], "unhealthy")
        finally:
            db_manager.pool = original_pool

    def test_health_check_endpoint_healthy(self):
        # Mock database connection pool ping success
        from app.backend.main import db_manager
        original_pool = db_manager.pool
        
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 1
        
        # Mock connection context manager behavior
        class MockAcquireContext:
            async def __aenter__(self):
                return mock_conn
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
                
        mock_pool.acquire.return_value = MockAcquireContext()
        db_manager.pool = mock_pool
        
        try:
            response = self.client.get("/api/health")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()
            self.assertEqual(data["status"], "online")
            self.assertEqual(data["services"]["database"]["status"], "healthy")
        finally:
            db_manager.pool = original_pool

    def test_current_traffic_viewport_validation(self):
        # Missing query parameters should return 422 Unprocessable Entity
        response = self.client.get("/api/current-traffic")
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        # Invalid bounds: min >= max should return 400 Bad Request
        response = self.client.get("/api/current-traffic?min_lon=10.0&min_lat=10.0&max_lon=5.0&max_lat=15.0")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("min_lon must be strictly less than max_lon", response.json()["detail"])

    def test_current_traffic_success(self):
        # Configure the default mock connection's return value
        self.mock_conn.fetch.return_value = [
            {
                "segment_id": 1,
                "osm_id": 10001,
                "name": "Main St",
                "geometry_json": '{"type": "LineString", "coordinates": [[-122.4, 37.7], [-122.3, 37.8]]}',
                "speed_limit": 50,
                "length": 1500.5,
                "current_speed": 42.3,
                "congestion_score": 0.15,
                "reading_timestamp": datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
            }
        ]

        response = self.client.get("/api/current-traffic?min_lon=-122.5&min_lat=37.6&max_lon=-122.2&max_lat=37.9")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 1)
        
        feat = data["features"][0]
        self.assertEqual(feat["type"], "Feature")
        self.assertEqual(feat["geometry"]["type"], "LineString")
        self.assertEqual(feat["properties"]["name"], "Main St")
        self.assertEqual(feat["properties"]["congestion_score"], 0.15)

    def test_weather_endpoint_success(self):
        # Configure the default mock connection's return value
        self.mock_conn.fetchrow.return_value = {
            "id": "a897b98a-f5e3-4b68-b769-cf563604f35e",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "temperature": 18.5,
            "rain_intensity": 0.0,
            "visibility": 10000.0,
            "timestamp": datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc),
            "distance_meters": 124.5
        }

        response = self.client.get("/api/weather?lat=37.775&lon=-122.420")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data["temperature"], 18.5)
        self.assertEqual(data["distance_meters"], 124.5)
        self.assertEqual(data["id"], "a897b98a-f5e3-4b68-b769-cf563604f35e")

    def test_incidents_endpoint_success(self):
        # Configure the default mock connection's return value
        self.mock_conn.fetch.return_value = [
            {
                "id": "e58df73a-4422-48df-bdfd-7c25c34e06bc",
                "incident_type": "accident",
                "description": "Minor fender bender on 101",
                "geometry_json": '{"type": "Point", "coordinates": [-122.401, 37.785]}',
                "severity": "medium",
                "status": "active",
                "created_at": datetime(2026, 7, 13, 11, 45, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 7, 13, 11, 45, 0, tzinfo=timezone.utc)
            }
        ]

        response = self.client.get("/api/incidents?severity=medium")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 1)
        
        feat = data["features"][0]
        self.assertEqual(feat["geometry"]["type"], "Point")
        self.assertEqual(feat["properties"]["incident_type"], "accident")
        self.assertEqual(feat["properties"]["severity"], "medium")

    def test_analytics_trends_network_wide_success(self):
        # Configure the default mock connection's return value
        self.mock_conn.fetch.return_value = [
            {
                "day_of_week": 1,
                "hour_of_day": 8,
                "avg_speed": 45.2,
                "avg_congestion": 0.42,
                "reading_count": 15,
                "daily_avg_speed": 55.4,
                "speed_diff_from_daily_avg": -10.2,
                "speed_change_from_prev_hour": -8.5,
                "speed_rank": 22
            },
            {
                "day_of_week": 1,
                "hour_of_day": 9,
                "avg_speed": 40.5,
                "avg_congestion": 0.58,
                "reading_count": 15,
                "daily_avg_speed": 55.4,
                "speed_diff_from_daily_avg": -14.9,
                "speed_change_from_prev_hour": -4.7,
                "speed_rank": 24
            }
        ]

        response = self.client.get("/api/analytics/trends")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertIsNone(data["segment_id"])
        self.assertEqual(len(data["trends"]), 2)
        
        trend = data["trends"][0]
        self.assertEqual(trend["day_of_week"], 1)
        self.assertEqual(trend["day_name"], "Monday")
        self.assertEqual(trend["hour_of_day"], 8)
        self.assertEqual(trend["avg_speed"], 45.2)
        self.assertEqual(trend["speed_rank"], 22)

    def test_analytics_trends_segment_not_found(self):
        # Mock checking segment exists (returns False)
        self.mock_conn.fetchval.return_value = False

        response = self.client.get("/api/analytics/trends?segment_id=999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Road segment with ID 999 not found", response.json()["detail"])

    def test_analytics_trends_segment_success(self):
        # Mock fetchval to return True for checking segment exists, and fetch to return results
        async def mock_fetchval(query, *args):
            if "EXISTS" in query:
                return True
            return None
            
        self.mock_conn.fetchval = mock_fetchval
        
        self.mock_conn.fetch.return_value = [
            {
                "day_of_week": 2,
                "hour_of_day": 12,
                "avg_speed": 62.1,
                "avg_congestion": 0.05,
                "reading_count": 10,
                "daily_avg_speed": 60.5,
                "speed_diff_from_daily_avg": 1.6,
                "speed_change_from_prev_hour": 2.1,
                "speed_rank": 5
            }
        ]

        response = self.client.get("/api/analytics/trends?segment_id=45")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data["segment_id"], 45)
        self.assertEqual(len(data["trends"]), 1)
        
        trend = data["trends"][0]
        self.assertEqual(trend["day_of_week"], 2)
        self.assertEqual(trend["day_name"], "Tuesday")
        self.assertEqual(trend["hour_of_day"], 12)
        self.assertEqual(trend["avg_speed"], 62.1)

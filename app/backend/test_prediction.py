import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from fastapi import status

from app.backend.main import app, get_db
from app.ml.model import TravelTimeModel

class TestPredictionAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides.clear()
        
        # Mock database connection
        self.mock_conn = AsyncMock()
        async def override_get_db():
            yield self.mock_conn
        app.dependency_overrides[get_db] = override_get_db

    def test_custom_prediction_endpoint_success(self):
        payload = {
            "length_meters": 5000.0,
            "speed_limit_kmh": 100.0,
            "congestion_score": 0.5,
            "rain_intensity": 2.0,
            "temperature": 15.0
        }
        
        response = self.client.post("/api/predict", json=payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertIn("predicted_time_seconds", data)
        self.assertIn("free_flow_time_seconds", data)
        self.assertIn("congestion_multiplier", data)
        self.assertEqual(data["free_flow_time_seconds"], 180.0) # 5000 / (100/3.6) = 180

    def test_custom_prediction_validation_error(self):
        # Invalid values: length_meters <= 0
        payload = {
            "length_meters": 0.0,
            "speed_limit_kmh": 100.0,
            "congestion_score": 0.5
        }
        response = self.client.post("/api/predict", json=payload)
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_segment_prediction_endpoint_success(self):
        # Configure database mocks
        self.mock_conn.fetchrow.side_effect = [
            # Segment metadata mock
            {
                "id": 108,
                "name": "I-80 E (Bay Bridge)",
                "speed_limit": 100.0,
                "length": 6500.0,
                "start_lon": -122.385,
                "start_lat": 37.798,
                "end_lon": -122.315,
                "end_lat": 37.825
            },
            # Weather snapshot mock
            {
                "temperature": 16.5,
                "rain_intensity": 0.0
            }
        ]
        
        # Segment congestion rating mock
        self.mock_conn.fetchval.side_effect = [
            0.28,             # Congestion score
            uuid4()           # Logged prediction UUID
        ]

        response = self.client.get("/api/predict/segment/108")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data["segment_id"], 108)
        self.assertEqual(data["name"], "I-80 E (Bay Bridge)")
        self.assertEqual(data["congestion_score"], 0.28)
        self.assertEqual(data["rain_intensity"], 0.0)
        self.assertEqual(data["temperature"], 16.5)
        self.assertIn("predicted_time_seconds", data)
        self.assertIn("prediction_id", data)

    def test_segment_prediction_not_found(self):
        self.mock_conn.fetchrow.return_value = None # Segment doesn't exist
        
        response = self.client.get("/api/predict/segment/99999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("segment with ID 99999 not found", response.json()["detail"])


class TestMLModel(unittest.TestCase):
    def test_model_prediction_mechanics(self):
        model = TravelTimeModel()
        
        # Test default weights prediction
        # length = 1000m, speed_limit = 36km/h (10m/s). Free flow = 100s.
        # Under free flow (congestion=0, rain=0, temp=20): multiplier should be w0 = 1.0 -> 100s.
        pred_free = model.predict(1000.0, 36.0, 0.0, 0.0, 20.0)
        self.assertEqual(pred_free, 100.0)
        
        # Under heavy congestion (congestion=1.0, rain=0, temp=20): multiplier should be w0+w1 = 4.0 -> 400s.
        pred_jam = model.predict(1000.0, 36.0, 1.0, 0.0, 20.0)
        self.assertEqual(pred_jam, 400.0)

    def test_model_training_fit(self):
        model = TravelTimeModel()
        
        # Generate training dataset where: actual_time = free_flow_time * (1.2 + 2.5 * congestion + 0.1 * rain)
        dataset = []
        for i in range(100):
            congestion = i / 100.0
            rain = (i % 5) * 1.0
            temp = 20.0
            
            # Use 36km/h speed limit (10m/s), length=1000m -> free-flow = 100s
            free_flow = 100.0
            mult = 1.2 + 2.5 * congestion + 0.1 * rain
            actual = free_flow * mult
            
            dataset.append({
                "length": 1000.0,
                "speed_limit": 36.0,
                "congestion_score": congestion,
                "rain_intensity": rain,
                "temperature": temp,
                "actual_time": actual
            })
            
        fit_results = model.fit(dataset, epochs=1000, lr=0.05)
        self.assertEqual(fit_results["status"], "success")
        self.assertEqual(fit_results["samples"], 100)
        
        # Verify that weights drifted closer to the generative parameters (w0=1.2, w1=2.5, w2=0.1)
        self.assertAlmostEqual(model.w0, 1.2, delta=0.3)
        self.assertAlmostEqual(model.w1, 2.5, delta=0.3)
        self.assertAlmostEqual(model.w2, 0.1, delta=0.1)

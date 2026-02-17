"""
Basic tests for KM Track API endpoints
Testing FastAPI application with all 18+ endpoints
"""

import pytest
from starlette.testclient import TestClient
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


class TestHealthEndpoints:
    """Test system health endpoints"""
    
    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service" in data
        assert "version" in data


class TestEventEndpoints:
    """Test event-related endpoints"""
    
    def test_get_current_event(self, client):
        """Test current event endpoint"""
        response = client.get("/api/current-event")
        assert response.status_code == 200
        data = response.json()
        assert "event" in data
        assert "name" in data
    
    def test_get_events_list(self, client):
        """Test events list endpoint"""
        response = client.get("/api/events")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "events" in data


class TestRaceConfigEndpoints:
    """Test race configuration endpoints"""
    
    def test_get_race_config(self, client):
        """Test race config endpoint"""
        response = client.get("/api/race-config")
        assert response.status_code == 200
        data = response.json()
        assert "total_distance" in data


class TestAnalyticsEndpoints:
    """Test analytics endpoints"""
    
    def test_get_registered_runners(self, client):
        """Test registered runners endpoint with database integration"""
        response = client.get("/api/registered-runners")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "runners" in data
        assert isinstance(data["runners"], list)
        
        # Verify data structure
        if data["runners"]:
            runner = data["runners"][0]
            assert "id" in runner
            assert "name" in runner
            assert "surname" in runner
            assert "full_name" in runner
            assert "category" in runner
    
    def test_get_registered_runners_with_limit(self, client):
        """Test registered runners endpoint with limit parameter"""
        response = client.get("/api/registered-runners?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] <= 5


class TestPageEndpoints:
    """Test HTML page endpoints"""
    
    def test_home_page(self, client):
        """Test home page"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_tracker_page(self, client):
        """Test tracker page"""
        response = client.get("/tracker")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_analytics_page(self, client):
        """Test analytics page"""
        response = client.get("/analytics")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestAPIStatus:
    """Test API status endpoint"""
    
    def test_api_status(self, client):
        """Test API status endpoint"""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

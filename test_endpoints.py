#!/usr/bin/env python
"""
Simple test script for KM Track API
Tests database integration and main endpoints
"""

import subprocess
import json
import time
import sys

BASE_URL = "http://localhost:8000"

def run_curl(endpoint: str, description: str) -> dict:
    """Run curl command and return JSON response"""
    url = f"{BASE_URL}{endpoint}"
    try:
        result = subprocess.run(
            ["curl", "-s", url],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                print(f"✓ {description}: SUCCESS")
                return {"status": "success", "data": data}
            except json.JSONDecodeError:
                print(f"✗ {description}: Invalid JSON response")
                return {"status": "error", "error": "Invalid JSON"}
        else:
            print(f"✗ {description}: FAILED")
            return {"status": "error", "error": result.stderr}
    except Exception as e:
        print(f"✗ {description}: {str(e)}")
        return {"status": "error", "error": str(e)}


def test_endpoints():
    """Test all main endpoints"""
    print("\n" + "="*60)
    print("KM TRACK API TEST SUITE")
    print("="*60 + "\n")
    
    tests = [
        # System endpoints
        ("/health", "Health Check"),
        ("/api/status", "API Status"),
        
        # Event endpoints
        ("/api/current-event", "Current Event"),
        ("/api/events", "Events List"),
        
        # Config endpoints
        ("/api/race-config", "Race Configuration"),
        
        # Analytics endpoints (Database Integration)
        ("/api/registered-runners", "Registered Runners (Database)"),
        ("/api/registered-runners?limit=5", "Registered Runners with Limit"),
        
        # Page endpoints
        ("/", "Home Page"),
        ("/tracker", "Tracker Page"),
        ("/analytics", "Analytics Page"),
    ]
    
    results = []
    for endpoint, description in tests:
        result = run_curl(endpoint, description)
        results.append({
            "endpoint": endpoint,
            "description": description,
            "result": result["status"]
        })
        time.sleep(0.1)  # Small delay between requests
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60 + "\n")
    
    passed = sum(1 for r in results if r["result"] == "success")
    total = len(results)
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%\n")
    
    # Detailed database test
    print("DATABASE INTEGRATION TEST:")
    db_result = run_curl("/api/registered-runners", "Database Endpoint")
    if db_result["status"] == "success":
        data = db_result["data"]
        runner_count = data.get("total", 0)
        runners = data.get("runners", [])
        
        print(f"  - Total runners in database: {runner_count}")
        if runners:
            first_runner = runners[0]
            print(f"  - First runner: {first_runner.get('full_name')}")
            print(f"  - Categories: {[r.get('category') for r in runners[:3]]}")
            print("\n✓ Database integration is working correctly!")
        else:
            print("✗ No runners found in database")
    else:
        print("✗ Database integration test failed")
    
    return passed == total


if __name__ == "__main__":
    print("\nWaiting for server to be ready...")
    time.sleep(1)
    
    success = test_endpoints()
    sys.exit(0 if success else 1)

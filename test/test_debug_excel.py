from fastapi.testclient import TestClient
from app.routes.main import app
from unittest.mock import patch

client = TestClient(app)

def test_debug():
    mock_attendance = [
        {
            "uid": 1,
            "user_id": "USR001",
            "name": "Juan Perez",
            "timestamp": "2025-05-27 08:30:00",
            "status": "IN"
        }
    ]

    with patch('app.routes.users.ZKService.get_attendance_records', return_value=mock_attendance):
        print("\n=== Test 1: JSON Response ===")
        response = client.get("/users/attendance")
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Content: {response.json()}")

        print("\n=== Test 2: Excel Response ===")
        response = client.get("/users/attendance?export=excel")
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Content-Disposition: {response.headers.get('content-disposition')}")
        print(f"Content Length: {len(response.content)}")
        print(f"Content (first 100 bytes): {response.content[:100]}")

if __name__ == "__main__":
    test_debug()

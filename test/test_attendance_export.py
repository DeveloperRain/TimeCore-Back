from fastapi.testclient import TestClient
from app.routes.main import app
from unittest.mock import patch, MagicMock

client = TestClient(app)


def test_get_attendance_json():
    """Test getting attendance as JSON"""
    mock_attendance = [
        {
            "uid": 1,
            "user_id": "USR001",
            "name": "Juan Perez",
            "timestamp": "2025-05-27 08:30:00",
            "status": "IN"
        },
        {
            "uid": 2,
            "user_id": "USR002",
            "name": "Maria Garcia",
            "timestamp": "2025-05-27 09:00:00",
            "status": "IN"
        }
    ]

    with patch('app.routes.users.ZKService.get_attendance_records', return_value=mock_attendance):
        response = client.get("/users/attendance")
        assert response.status_code == 200
        assert len(response.json()) == 2
        assert response.json()[0]["user_id"] == "USR001"
        print("[OK] Test GET /users/attendance JSON passed")


def test_get_attendance_download_excel():
    """Test downloading attendance as Excel file"""
    mock_attendance = [
        {
            "uid": 1,
            "user_id": "USR001",
            "name": "Juan Perez",
            "timestamp": "2025-05-27 08:30:00",
            "status": "IN"
        },
        {
            "uid": 2,
            "user_id": "USR002",
            "name": "Maria Garcia",
            "timestamp": "2025-05-27 09:00:00",
            "status": "IN"
        }
    ]

    with patch('app.routes.users.ZKService.get_attendance_records', return_value=mock_attendance):
        response = client.get("/users/attendance/download")
        assert response.status_code == 200
        assert "spreadsheetml" in response.headers["content-type"]
        assert "asistencias.xlsx" in response.headers["content-disposition"]
        assert len(response.content) > 0
        print("[OK] Test GET /users/attendance/download Excel passed")


def test_get_attendance_both_endpoints():
    """Test that both endpoints work together"""
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
        # Get JSON
        response_json = client.get("/users/attendance")
        assert response_json.status_code == 200
        assert response_json.headers["content-type"] == "application/json"

        # Download Excel
        response_excel = client.get("/users/attendance/download")
        assert response_excel.status_code == 200
        assert "spreadsheetml" in response_excel.headers["content-type"]

        print("[OK] Test both endpoints work together")


if __name__ == "__main__":
    test_get_attendance_json()
    test_get_attendance_download_excel()
    test_get_attendance_both_endpoints()
    print("\n[SUCCESS] All tests passed!")



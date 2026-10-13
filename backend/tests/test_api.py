from datetime import timedelta

import pytest

from app import create_app
from extensions import db
from models import (
    Alert,
    Attendance,
    ClassSession,
    EnergyReading,
    Student,
    utcnow,
)
from services import integrate_readings, integrate_readings_by_source, seed_demo_data


@pytest.fixture()
def app():
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "ALLOW_DEMO_RESET": True,
            "ENERGY_THRESHOLD_WATTS": 50,
            "WASTE_DURATION_SECONDS": 10,
            "MAX_READING_GAP_SECONDS": 900,
            "ELECTRICITY_TARIFF_INR": 8,
        }
    )
    with application.app_context():
        db.create_all()
        seed_demo_data()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def payload(response):
    return response.get_json()["data"]


def test_student_registration(client):
    response = client.post(
        "/api/students",
        json={"student_id": "STU-NEW", "name": "Asha Rao", "department": "Engineering"},
    )
    assert response.status_code == 201
    assert payload(response)["student_id"] == "STU-NEW"
    duplicate = client.post(
        "/api/students",
        json={"student_id": "STU-NEW", "name": "Asha Rao", "department": "Engineering"},
    )
    assert duplicate.status_code == 409


def active_session_id(app):
    with app.app_context():
        return ClassSession.query.filter_by(status="active").first().id


def qr_for(client, session_id):
    response = client.post(f"/api/sessions/{session_id}/qr")
    assert response.status_code == 200
    return payload(response)["token"]


def test_attendance_mark_and_duplicate_rejection(client, app):
    session_id = active_session_id(app)
    token = qr_for(client, session_id)
    marked = client.post(
        "/api/attendance/mark",
        json={"student_id": "STU-009", "session_id": session_id, "token": token, "method": "manual"},
    )
    assert marked.status_code == 201
    assert payload(marked)["occupancy"] == 9
    duplicate = client.post(
        "/api/attendance/mark",
        json={"student_id": "STU-009", "session_id": session_id, "token": token},
    )
    assert duplicate.status_code == 409
    assert "already" in duplicate.get_json()["error"]


def test_attendance_rejects_invalid_token_and_closed_session(client, app):
    session_id = active_session_id(app)
    invalid = client.post(
        "/api/attendance/mark",
        json={"student_id": "STU-009", "session_id": session_id, "token": "not-valid"},
    )
    assert invalid.status_code == 401
    token = qr_for(client, session_id)
    with app.app_context():
        session = db.session.get(ClassSession, session_id)
        session.qr_expires_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
    expired = client.post(
        "/api/attendance/mark",
        json={"student_id": "STU-009", "session_id": session_id, "token": token},
    )
    assert expired.status_code == 401
    token = qr_for(client, session_id)
    with app.app_context():
        session = db.session.get(ClassSession, session_id)
        session.end_time = utcnow() - timedelta(minutes=1)
        db.session.commit()
    out_of_window = client.post(
        "/api/attendance/mark",
        json={"student_id": "STU-009", "session_id": session_id, "token": token},
    )
    assert out_of_window.status_code == 409
    with app.app_context():
        session = db.session.get(ClassSession, session_id)
        session.end_time = utcnow() + timedelta(hours=1)
        db.session.commit()
    closed = client.patch(f"/api/sessions/{session_id}", json={"status": "completed"})
    assert closed.status_code == 200
    rejected = client.post(
        "/api/attendance/mark",
        json={"student_id": "STU-009", "session_id": session_id, "token": token},
    )
    assert rejected.status_code == 409


def test_attendance_method_and_duplicate_active_session_validation(client, app):
    session_id = active_session_id(app)
    token = qr_for(client, session_id)
    invalid_method = client.post(
        "/api/attendance/mark",
        json={
            "student_id": "STU-009",
            "session_id": session_id,
            "token": token,
            "method": "unknown",
        },
    )
    assert invalid_method.status_code == 400
    with app.app_context():
        session = db.session.get(ClassSession, session_id)
        room_id = session.classroom_id
    duplicate_active = client.post(
        "/api/sessions",
        json={
            "classroom_id": room_id,
            "subject": "Second simultaneous class",
            "start_time": utcnow().isoformat(),
            "end_time": (utcnow() + timedelta(hours=1)).isoformat(),
            "status": "active",
        },
    )
    assert duplicate_active.status_code == 409


def test_occupancy_calculation_and_zero_attendance_is_not_empty(client, app):
    with app.app_context():
        session = ClassSession.query.filter_by(classroom_id=1, status="active").first()
        student = Student.query.filter_by(student_id="STU-009").first()
        db.session.add(
            Attendance(
                student=student,
                session=session,
                method="manual",
                status="pending",
            )
        )
        db.session.commit()
    rooms = payload(client.get("/api/classrooms"))
    active_zero = next(room for room in rooms if room["room_code"] == "SCI-215")
    assert active_zero["occupancy"] == 0
    assert active_zero["occupancy_status"] == "Awaiting occupancy confirmation"
    occupied = next(room for room in rooms if room["room_code"] == "ENG-101")
    assert occupied["occupancy"] == 8


def test_wastage_detection_and_active_alert_deduplication(client):
    rooms = payload(client.get("/api/classrooms"))
    empty_room = next(room for room in rooms if room["room_code"] == "ENG-204")
    response = client.post(
        "/api/demo/simulate-empty-room-wastage",
        json={"classroom_id": empty_room["id"], "confirm_empty": True, "power_watts": 320},
    )
    assert response.status_code == 201
    assert payload(response)["incident_detected"] is True
    repeat = client.post(
        "/api/demo/simulate-empty-room-wastage",
        json={"classroom_id": empty_room["id"], "confirm_empty": True, "power_watts": 320},
    )
    assert repeat.status_code == 201
    open_alerts = payload(client.get("/api/alerts?status=open"))
    assert sum(alert["classroom"] == "ENG-204" for alert in open_alerts) == 1


def test_energy_integration_and_conservative_gap_handling(app):
    with app.app_context():
        room = db.session.query(ClassSession).first().classroom
        base = utcnow()
        readings = [
            EnergyReading(classroom=room, power_watts=100, recorded_at=base),
            EnergyReading(classroom=room, power_watts=200, recorded_at=base + timedelta(seconds=3600)),
            EnergyReading(classroom=room, power_watts=900, recorded_at=base + timedelta(days=1)),
        ]
        assert integrate_readings(readings, 3600) == pytest.approx(0.15)


def test_energy_sources_do_not_count_mixed_intervals_twice(app):
    with app.app_context():
        room = ClassSession.query.first().classroom
        base = utcnow()
        readings = [
            EnergyReading(classroom=room, power_watts=100, source="measured", recorded_at=base),
            EnergyReading(
                classroom=room,
                power_watts=200,
                source="simulated",
                recorded_at=base + timedelta(seconds=60),
            ),
            EnergyReading(
                classroom=room,
                power_watts=300,
                source="measured",
                recorded_at=base + timedelta(seconds=120),
            ),
        ]
        assert integrate_readings_by_source(readings, 900) == {
            "measured": 0,
            "simulated": 0,
        }


def test_cost_estimation_and_alert_resolution(client):
    room = next(room for room in payload(client.get("/api/classrooms")) if room["room_code"] == "ENG-204")
    result = payload(
        client.post(
            "/api/demo/simulate-empty-room-wastage",
            json={"classroom_id": room["id"], "confirm_empty": True, "power_watts": 320},
        )
    )
    assert result["incident_detected"] is True
    report = payload(client.get("/api/reports/energy"))
    assert report["potential_savings_inr"] == round(report["estimated_avoidable_kwh"] * 8, 2)
    active = payload(client.get("/api/alerts?status=open"))
    alert = next(item for item in active if item["classroom"] == "ENG-204")
    resolved = client.patch(f"/api/alerts/{alert['id']}", json={"status": "resolved"})
    assert resolved.status_code == 200
    assert payload(resolved)["status"] == "resolved"
    assert payload(client.get("/api/alerts?status=open")) == []


def test_energy_csv_export_keeps_savings_at_classroom_grain(client):
    response = client.get("/api/reports/energy/export")
    assert response.status_code == 200
    rows = response.get_data(as_text=True).strip().splitlines()
    assert rows[0].startswith("Classroom,Department,Energy (kWh)")
    assert len(rows) == 9
    filtered = client.get("/api/reports/energy?classroom_id=2")
    assert filtered.status_code == 200
    assert len(payload(filtered)["classrooms"]) == 1
    report = payload(client.get("/api/reports/energy"))
    assert report["alerts"]
    assert sum(item["estimated_avoidable_kwh"] for item in report["classrooms"]) == pytest.approx(
        report["estimated_avoidable_kwh"], abs=0.0001
    )


def test_clearing_power_resolves_active_incident_and_alert(client):
    room = next(room for room in payload(client.get("/api/classrooms")) if room["room_code"] == "ENG-204")
    created = client.post(
        "/api/demo/simulate-empty-room-wastage",
        json={"classroom_id": room["id"], "confirm_empty": True, "power_watts": 320},
    )
    assert payload(created)["incident_detected"] is True
    cleared = client.post(
        "/api/energy/simulate",
        json={"classroom_id": room["id"], "power_watts": 0},
    )
    assert cleared.status_code == 201
    assert payload(client.get("/api/alerts?status=open")) == []
    incidents = payload(client.get("/api/reports/energy"))["incidents"]
    incident = next(item for item in incidents if item["classroom"] == "ENG-204")
    assert incident["status"] == "resolved"


def test_api_validation_and_demo_seed_idempotence(client):
    bad_student = client.post("/api/students", json={"student_id": "", "name": "", "department": ""})
    assert bad_student.status_code == 400
    bad_report = client.get("/api/reports/energy?start=2026-10-13T00:00:00Z&end=2026-10-01T00:00:00Z")
    assert bad_report.status_code == 400
    first = payload(client.post("/api/demo/seed"))
    second = payload(client.post("/api/demo/seed"))
    assert first["seeded"] is False
    assert second["seeded"] is False
    assert payload(client.get("/api/students"))[0]["student_id"]

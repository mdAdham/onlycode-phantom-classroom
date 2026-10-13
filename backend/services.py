import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (
    Alert,
    Attendance,
    Classroom,
    ClassSession,
    EnergyIncident,
    EnergyReading,
    Student,
    utcnow,
)


class ServiceError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def parse_datetime(value, field_name):
    if not isinstance(value, str):
        raise ServiceError(f"{field_name} must be an ISO-8601 datetime.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError as error:
        raise ServiceError(f"{field_name} must be a valid ISO-8601 datetime.") from error


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session_qr(session):
    now = utcnow()
    if session.start_time > now or session.end_time < now:
        raise ServiceError("This class session is not within its attendance window.", 409)
    token = secrets.token_urlsafe(32)
    session.qr_token_hash = token_digest(token)
    session.qr_expires_at = now + timedelta(minutes=15)
    db.session.commit()
    return {
        "session_id": session.id,
        "token": token,
        "expires_at": session.qr_expires_at.replace(tzinfo=timezone.utc).isoformat(),
    }


def mark_attendance(student_code, session_id, token, method="manual"):
    if method not in ("manual", "qr"):
        raise ServiceError("method must be manual or qr.")
    student = Student.query.filter_by(student_id=student_code.strip()).first()
    if not student or not student.is_active:
        raise ServiceError("Student ID was not found or the student is inactive.", 404)
    session = db.session.get(ClassSession, session_id)
    if not session:
        raise ServiceError("Class session was not found.", 404)
    if not isinstance(token, str) or not token or not session.qr_token_hash or not secrets.compare_digest(
        session.qr_token_hash, token_digest(token)
    ):
        raise ServiceError("Invalid or expired session QR token.", 401)
    if not session.qr_expires_at or session.qr_expires_at < utcnow():
        raise ServiceError("This QR token has expired. Generate a new session QR code.", 401)
    now = utcnow()
    if session.status != "active" or session.start_time > now or session.end_time < now:
        raise ServiceError("Attendance is closed for this session.", 409)
    if Attendance.query.filter_by(student_id=student.id, session_id=session.id).first():
        raise ServiceError("Attendance has already been marked for this student.", 409)
    attendance = Attendance(
        student_id=student.id,
        session_id=session.id,
        method=method,
    )
    db.session.add(attendance)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise ServiceError("Attendance has already been marked for this student.", 409) from error
    return attendance


def is_confirmed_empty(classroom):
    if any(session.status == "active" for session in classroom.sessions):
        return False
    if classroom.empty_confirmed:
        return True
    latest_session = max(classroom.sessions, key=lambda session: session.start_time, default=None)
    return latest_session is not None and latest_session.status == "completed"


def integrate_readings(readings, max_gap_seconds):
    """Integrate adjacent readings, excluding missing/too-distant intervals."""
    energy_kwh = 0.0
    for previous, current in zip(readings, readings[1:]):
        seconds = (current.recorded_at - previous.recorded_at).total_seconds()
        if 0 < seconds <= max_gap_seconds:
            average_watts = (previous.power_watts + current.power_watts) / 2
            energy_kwh += average_watts * (seconds / 3600) / 1000
    return energy_kwh


def integrate_readings_by_source(readings, max_gap_seconds):
    totals = {"measured": 0.0, "simulated": 0.0}
    for previous, current in zip(readings, readings[1:]):
        seconds = (current.recorded_at - previous.recorded_at).total_seconds()
        if (
            previous.source == current.source
            and current.source in totals
            and 0 < seconds <= max_gap_seconds
        ):
            average_watts = (previous.power_watts + current.power_watts) / 2
            totals[current.source] += average_watts * (seconds / 3600) / 1000
    return totals


def evaluate_wastage(classroom, config):
    active_incident = EnergyIncident.query.filter_by(
        classroom_id=classroom.id, status="active"
    ).first()
    latest = (
        EnergyReading.query.filter_by(classroom_id=classroom.id)
        .order_by(EnergyReading.recorded_at.desc())
        .first()
    )
    if (
        not latest
        or not is_confirmed_empty(classroom)
        or latest.power_watts <= config["ENERGY_THRESHOLD_WATTS"]
    ):
        if active_incident:
            active_incident.status = "resolved"
            active_incident.ended_at = latest.recorded_at if latest else utcnow()
            if active_incident.alert and active_incident.alert.status != "resolved":
                active_incident.alert.status = "resolved"
                active_incident.alert.resolved_at = utcnow()
            db.session.commit()
        return None

    high_readings = (
        EnergyReading.query.filter(
            EnergyReading.classroom_id == classroom.id,
            EnergyReading.power_watts > config["ENERGY_THRESHOLD_WATTS"],
        )
        .order_by(EnergyReading.recorded_at.desc())
        .limit(10)
        .all()
    )
    high_readings.reverse()
    if not high_readings:
        return None
    continuous = [high_readings[-1]]
    for reading in reversed(high_readings[:-1]):
        gap = (continuous[0].recorded_at - reading.recorded_at).total_seconds()
        if gap <= config["MAX_READING_GAP_SECONDS"]:
            continuous.insert(0, reading)
        else:
            break
    duration = (
        (continuous[-1].recorded_at - continuous[0].recorded_at).total_seconds()
        if len(continuous) > 1
        else 0
    )
    if duration < config["WASTE_DURATION_SECONDS"]:
        return None

    if not active_incident:
        alert = Alert(
            classroom_id=classroom.id,
            type="Electricity wastage",
            severity="high" if latest.power_watts > config["ENERGY_THRESHOLD_WATTS"] * 5 else "medium",
            message=(
                f"{classroom.room_code} is confirmed empty while drawing "
                f"{latest.power_watts:.0f} W."
            ),
            recommended_action="Check and switch off unnecessary lights, fans, or AC.",
            detected_power_watts=latest.power_watts,
        )
        db.session.add(alert)
        db.session.flush()
        active_incident = EnergyIncident(
            classroom_id=classroom.id,
            started_at=continuous[0].recorded_at,
            peak_power_watts=max(item.power_watts for item in continuous),
            alert_id=alert.id,
        )
        db.session.add(active_incident)
    else:
        active_incident.peak_power_watts = max(
            active_incident.peak_power_watts, latest.power_watts
        )
        if active_incident.alert:
            active_incident.alert.detected_power_watts = latest.power_watts

    incident_readings = (
        EnergyReading.query.filter(
            EnergyReading.classroom_id == classroom.id,
            EnergyReading.recorded_at >= active_incident.started_at,
        )
        .order_by(EnergyReading.recorded_at.asc())
        .all()
    )
    active_incident.estimated_kwh = integrate_readings(
        incident_readings, config["MAX_READING_GAP_SECONDS"]
    )
    db.session.commit()
    return active_incident


def seed_demo_data():
    if Student.query.first():
        return False
    now = utcnow()
    departments = ["Engineering", "Science", "Business", "Arts"]
    classroom_specs = [
        ("ENG-101", "Engineering", 40, "Dr. Asha Rao"),
        ("ENG-204", "Engineering", 36, "Prof. Nikhil Shah"),
        ("SCI-110", "Science", 32, "Dr. Meera Iyer"),
        ("SCI-215", "Science", 48, "Dr. Omar Khan"),
        ("BUS-105", "Business", 30, "Prof. Kavya Menon"),
        ("BUS-202", "Business", 42, "Dr. Rohan Patel"),
        ("ART-120", "Arts", 28, "Prof. Leena Das"),
        ("ART-208", "Arts", 35, "Dr. Arjun Nair"),
    ]
    rooms = []
    for code, department, capacity, staff in classroom_specs:
        room = Classroom(
            room_code=code,
            department=department,
            capacity=capacity,
            responsible_staff=staff,
            empty_confirmed=code in ("ENG-204", "ART-208"),
        )
        db.session.add(room)
        rooms.append(room)

    students = []
    for index in range(1, 49):
        student = Student(
            student_id=f"STU-{index:03}",
            name=f"{['Aarav', 'Diya', 'Ishaan', 'Mira', 'Kabir', 'Anaya'][index % 6]} "
            f"{['Sharma', 'Patel', 'Rao', 'Iyer', 'Khan', 'Das'][index % 6]}",
            department=departments[(index - 1) % len(departments)],
        )
        db.session.add(student)
        students.append(student)
    db.session.flush()

    session_specs = [
        (0, "Applied Data Systems", "active", 8),
        (1, "Embedded Systems", "completed", 0),
        (2, "Environmental Chemistry", "active", 5),
        (3, "Research Methods", "active", 0),
        (4, "Campus Finance", "completed", 0),
        (5, "Operations Strategy", "active", 4),
        (6, "Visual Communication", "scheduled", 0),
        (7, "Design History", "completed", 0),
    ]
    for room_index, subject, status, attendees in session_specs:
        if status in ("active", "scheduled"):
            rooms[room_index].empty_confirmed = False
        start_offset = -1 if status == "active" else (1 if status == "scheduled" else -5)
        session = ClassSession(
            classroom=rooms[room_index],
            subject=subject,
            start_time=now + timedelta(hours=start_offset),
            end_time=now + timedelta(hours=3 if status == "active" else start_offset + 2),
            status=status,
        )
        db.session.add(session)
        for student in students[room_index * 5 : room_index * 5 + attendees]:
            db.session.add(
                Attendance(student=student, session=session, method="manual", status="verified")
            )
    db.session.flush()

    for room_index, room in enumerate(rooms):
        base_watts = [680, 420, 540, 0, 350, 610, 0, 230][room_index]
        for offset in range(23, -1, -1):
            recorded = now - timedelta(hours=offset)
            variation = 25 if offset % 3 else -15
            watts = max(base_watts + variation, 0)
            if room_index == 1 and offset <= 1:
                watts = 310
            if room_index == 3:
                watts = 0
            db.session.add(
                EnergyReading(
                    classroom=room,
                    power_watts=watts,
                    lights_on=watts > 50,
                    fans_on=watts > 250,
                    ac_on=watts > 500,
                    source="simulated",
                    recorded_at=recorded,
                )
            )
        for minutes_ago in range(60, 0, -5):
            watts = 0 if room_index == 3 else (
                310 if room_index == 1 else max(base_watts + (10 if minutes_ago % 2 else -10), 0)
            )
            db.session.add(
                EnergyReading(
                    classroom=room,
                    power_watts=watts,
                    lights_on=watts > 50,
                    fans_on=watts > 250,
                    ac_on=watts > 500,
                    source="simulated",
                    recorded_at=now - timedelta(minutes=minutes_ago),
                )
            )
    db.session.flush()

    # The active example makes the first dashboard useful before the live demo.
    alert = Alert(
        classroom=rooms[1],
        type="Electricity wastage",
        severity="high",
        message="ENG-204 is confirmed empty while drawing 310 W.",
        recommended_action="Check and switch off unnecessary lights, fans, or AC.",
        status="open",
        detected_power_watts=310,
        created_at=now - timedelta(minutes=12),
    )
    db.session.add(alert)
    db.session.flush()
    incident_start = now - timedelta(minutes=20)
    incident_readings = (
        EnergyReading.query.filter(
            EnergyReading.classroom_id == rooms[1].id,
            EnergyReading.recorded_at >= incident_start,
        )
        .order_by(EnergyReading.recorded_at.asc())
        .all()
    )
    db.session.add(
        EnergyIncident(
            classroom=rooms[1],
            started_at=incident_start,
            peak_power_watts=310,
            estimated_kwh=integrate_readings(incident_readings, 900),
            status="active",
            alert_id=alert.id,
        )
    )
    db.session.add(
        Alert(
            classroom=rooms[4],
            type="Electricity wastage",
            severity="low",
            message="BUS-105 energy alert resolved after classroom check.",
            recommended_action="No further action required.",
            status="resolved",
            detected_power_watts=75,
            created_at=now - timedelta(days=1),
            resolved_at=now - timedelta(hours=22),
        )
    )
    db.session.commit()
    return True

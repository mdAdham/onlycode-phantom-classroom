import csv
import io
import math
from datetime import timedelta, timezone

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError

from config import Config
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
from services import (
    ServiceError,
    create_session_qr,
    evaluate_wastage,
    integrate_readings,
    integrate_readings_by_source,
    is_confirmed_empty,
    mark_attendance,
    parse_datetime,
    seed_demo_data,
)


def success(data, status=200):
    return jsonify({"data": data, "error": None}), status


def failure(message, status=400):
    return jsonify({"data": None, "error": message}), status


def body_object():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ServiceError("Request body must be a JSON object.")
    return body


def required_text(body, key, maximum=120):
    value = body.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ServiceError(f"{key} is required and must be at most {maximum} characters.")
    return value.strip()


def valid_positive_number(value, field, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ServiceError(f"{field} must be a number.")
    if not math.isfinite(value) or value > 100000:
        raise ServiceError(f"{field} must be finite and no greater than 100000.")
    if value < 0 or (not allow_zero and value == 0):
        raise ServiceError(f"{field} must be {'zero or greater' if allow_zero else 'greater than zero'}.")
    return float(value)


def boolean_field(body, key, default=False):
    value = body.get(key, default)
    if not isinstance(value, bool):
        raise ServiceError(f"{key} must be true or false.")
    return value


def get_date_range():
    now = utcnow()
    start = parse_datetime(request.args["start"], "start") if request.args.get("start") else now - timedelta(days=7)
    end = parse_datetime(request.args["end"], "end") if request.args.get("end") else now
    if start > end:
        raise ServiceError("start must be before or equal to end.")
    if (end - start).days > 366:
        raise ServiceError("Date range cannot exceed 366 days.")
    return start, end


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"])}},
    )

    @app.errorhandler(ServiceError)
    def handle_service_error(error):
        return failure(str(error), error.status_code)

    @app.errorhandler(404)
    def handle_not_found(_error):
        return failure("The requested resource was not found.", 404)

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(_error):
        db.session.rollback()
        return failure("The request conflicts with existing data.", 409)

    @app.errorhandler(500)
    def handle_server_error(_error):
        db.session.rollback()
        app.logger.exception("Unhandled API error")
        return failure("An unexpected server error occurred.", 500)

    @app.get("/api/health")
    def health():
        return success({"status": "ok"})

    @app.get("/api/dashboard")
    def dashboard():
        classrooms = Classroom.query.order_by(Classroom.room_code).all()
        active_sessions = ClassSession.query.filter_by(status="active").all()
        latest_by_room = []
        for room in classrooms:
            latest = (
                EnergyReading.query.filter_by(classroom_id=room.id)
                .order_by(EnergyReading.recorded_at.desc())
                .first()
            )
            if latest:
                latest_by_room.append(latest)
        active_alerts = Alert.query.filter(Alert.status.in_(("open", "acknowledged"))).count()
        incidents = EnergyIncident.query.filter_by(status="active").all()
        avoidable_kwh = sum(item.estimated_kwh for item in incidents)
        alerts = Alert.query.order_by(Alert.created_at.desc()).limit(5).all()
        return success(
            {
                "classroom_count": len(classrooms),
                "student_count": Student.query.filter_by(is_active=True).count(),
                "present_count": sum(
                    sum(record.status == "verified" for record in session.attendance)
                    for session in active_sessions
                ),
                "current_power_watts": round(sum(item.power_watts for item in latest_by_room), 1),
                "active_alert_count": active_alerts,
                "estimated_avoidable_kwh": round(avoidable_kwh, 4),
                "potential_savings_inr": round(avoidable_kwh * app.config["ELECTRICITY_TARIFF_INR"], 2),
                "tariff_inr_per_kwh": app.config["ELECTRICITY_TARIFF_INR"],
                "energy_threshold_watts": app.config["ENERGY_THRESHOLD_WATTS"],
                "demo_duration_seconds": app.config["WASTE_DURATION_SECONDS"],
                "classrooms": [room.to_dict() for room in classrooms],
                "recent_alerts": [item.to_dict() for item in alerts],
            }
        )

    @app.get("/api/dashboard/energy-trend")
    def energy_trend():
        start, end = get_date_range()
        readings = EnergyReading.query.filter(
            EnergyReading.recorded_at >= start, EnergyReading.recorded_at <= end
        ).order_by(EnergyReading.recorded_at.asc()).all()
        buckets = {}
        for reading in readings:
            label = reading.recorded_at.strftime("%d %b %H:%M")
            buckets.setdefault(label, {"label": label, "power_watts": 0, "rooms": 0})
            buckets[label]["power_watts"] += reading.power_watts
            buckets[label]["rooms"] += 1
        return success(list(buckets.values())[-48:])

    @app.get("/api/students")
    def students_list():
        query = Student.query
        search = request.args.get("search", "").strip()
        if len(search) > 120:
            raise ServiceError("search cannot exceed 120 characters.")
        if search:
            query = query.filter(
                db.or_(Student.name.ilike(f"%{search}%"), Student.student_id.ilike(f"%{search}%"))
            )
        return success([student.to_dict() for student in query.order_by(Student.name).limit(200).all()])

    @app.post("/api/students")
    def students_create():
        body = body_object()
        student_code = required_text(body, "student_id", 40)
        if Student.query.filter_by(student_id=student_code).first():
            raise ServiceError("A student with this student_id already exists.", 409)
        student = Student(
            student_id=student_code,
            name=required_text(body, "name"),
            department=required_text(body, "department", 80),
        )
        db.session.add(student)
        db.session.commit()
        return success(student.to_dict(), 201)

    @app.get("/api/students/<int:student_id>")
    def student_detail(student_id):
        student = db.session.get(Student, student_id)
        if not student:
            raise ServiceError("Student was not found.", 404)
        return success(student.to_dict())

    @app.get("/api/classrooms")
    def classrooms_list():
        search = request.args.get("search", "").strip()
        query = Classroom.query
        if search:
            query = query.filter(
                db.or_(Classroom.room_code.ilike(f"%{search}%"), Classroom.department.ilike(f"%{search}%"))
            )
        return success([room.to_dict() for room in query.order_by(Classroom.room_code).all()])

    @app.post("/api/classrooms")
    def classrooms_create():
        body = body_object()
        code = required_text(body, "room_code", 30)
        capacity = body.get("capacity")
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ServiceError("capacity must be a positive integer.")
        room = Classroom(
            room_code=code,
            department=required_text(body, "department", 80),
            capacity=capacity,
            responsible_staff=required_text(body, "responsible_staff"),
        )
        db.session.add(room)
        db.session.commit()
        return success(room.to_dict(), 201)

    @app.get("/api/classrooms/<int:classroom_id>")
    def classroom_detail(classroom_id):
        room = db.session.get(Classroom, classroom_id)
        if not room:
            raise ServiceError("Classroom was not found.", 404)
        readings = (
            EnergyReading.query.filter_by(classroom_id=room.id)
            .order_by(EnergyReading.recorded_at.desc())
            .limit(30)
            .all()
        )
        sessions = (
            ClassSession.query.filter_by(classroom_id=room.id)
            .order_by(ClassSession.start_time.desc())
            .limit(10)
            .all()
        )
        return success(
            {
                **room.to_dict(),
                "readings": [reading.to_dict() for reading in readings],
                "sessions": [session.to_dict() for session in sessions],
            }
        )

    @app.get("/api/sessions")
    def sessions_list():
        query = ClassSession.query
        status = request.args.get("status")
        if status:
            if status not in ("scheduled", "active", "completed"):
                raise ServiceError("status must be scheduled, active, or completed.")
            query = query.filter_by(status=status)
        return success(
            [item.to_dict() for item in query.order_by(ClassSession.start_time.desc()).limit(200).all()]
        )

    @app.post("/api/sessions")
    def sessions_create():
        body = body_object()
        classroom_id = body.get("classroom_id")
        room = (
            db.session.get(Classroom, classroom_id)
            if isinstance(classroom_id, int) and not isinstance(classroom_id, bool)
            else None
        )
        if not room:
            raise ServiceError("A valid classroom_id is required.")
        start_time = parse_datetime(body.get("start_time"), "start_time")
        end_time = parse_datetime(body.get("end_time"), "end_time")
        if start_time >= end_time:
            raise ServiceError("end_time must be after start_time.")
        status = body.get("status", "scheduled")
        if status not in ("scheduled", "active", "completed"):
            raise ServiceError("status must be scheduled, active, or completed.")
        session = ClassSession(
            classroom=room,
            subject=required_text(body, "subject"),
            start_time=start_time,
            end_time=end_time,
            status=status,
        )
        room.empty_confirmed = False
        db.session.add(session)
        db.session.commit()
        return success(session.to_dict(), 201)

    @app.patch("/api/sessions/<int:session_id>")
    def sessions_update(session_id):
        session = db.session.get(ClassSession, session_id)
        if not session:
            raise ServiceError("Class session was not found.", 404)
        body = body_object()
        status = body.get("status")
        if status not in ("scheduled", "active", "completed"):
            raise ServiceError("status must be scheduled, active, or completed.")
        if status == "active":
            other = ClassSession.query.filter(
                ClassSession.classroom_id == session.classroom_id,
                ClassSession.status == "active",
                ClassSession.id != session.id,
            ).first()
            if other:
                raise ServiceError("This classroom already has an active session.", 409)
        if status in ("scheduled", "active"):
            session.classroom.empty_confirmed = False
        session.status = status
        db.session.commit()
        return success(session.to_dict())

    @app.post("/api/sessions/<int:session_id>/qr")
    def sessions_qr(session_id):
        session = db.session.get(ClassSession, session_id)
        if not session:
            raise ServiceError("Class session was not found.", 404)
        now = utcnow()
        if session.status != "active" or session.start_time > now or session.end_time < now:
            raise ServiceError("QR codes can only be generated for active sessions.", 409)
        return success(create_session_qr(session))

    @app.post("/api/attendance/mark")
    def attendance_mark():
        body = body_object()
        session_id = body.get("session_id")
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise ServiceError("session_id must be an integer.")
        attendance = mark_attendance(
            required_text(body, "student_id", 40),
            session_id,
            body.get("token"),
            body.get("method", "manual"),
        )
        return success(
            {
                **attendance.to_dict(),
                "occupancy": len(attendance.session.attendance),
                "capacity": attendance.session.classroom.capacity,
            },
            201,
        )

    @app.get("/api/attendance")
    def attendance_list():
        query = Attendance.query
        session_id = request.args.get("session_id")
        if session_id:
            try:
                query = query.filter_by(session_id=int(session_id))
            except ValueError as error:
                raise ServiceError("session_id must be an integer.") from error
        records = query.order_by(Attendance.marked_at.desc()).limit(200).all()
        return success([item.to_dict() for item in records])

    @app.get("/api/attendance/session/<int:session_id>")
    def attendance_session(session_id):
        session = db.session.get(ClassSession, session_id)
        if not session:
            raise ServiceError("Class session was not found.", 404)
        records = Attendance.query.filter_by(session_id=session.id).order_by(Attendance.marked_at.desc()).all()
        return success(
            {
                "session": session.to_dict(),
                "records": [item.to_dict() for item in records],
            }
        )

    @app.get("/api/energy/readings")
    def energy_readings():
        classroom_id = request.args.get("classroom_id")
        limit = request.args.get("limit", "100")
        try:
            limit_value = int(limit)
        except ValueError as error:
            raise ServiceError("limit must be an integer.") from error
        if not 1 <= limit_value <= 500:
            raise ServiceError("limit must be between 1 and 500.")
        query = EnergyReading.query
        if classroom_id:
            try:
                query = query.filter_by(classroom_id=int(classroom_id))
            except ValueError as error:
                raise ServiceError("classroom_id must be an integer.") from error
        readings = query.order_by(EnergyReading.recorded_at.desc()).limit(limit_value).all()
        return success([item.to_dict() for item in readings])

    @app.post("/api/energy/readings")
    def energy_reading_create():
        body = body_object()
        classroom_id = body.get("classroom_id")
        room = (
            db.session.get(Classroom, classroom_id)
            if isinstance(classroom_id, int) and not isinstance(classroom_id, bool)
            else None
        )
        if not room:
            raise ServiceError("A valid classroom_id is required.")
        watts = valid_positive_number(body.get("power_watts"), "power_watts", allow_zero=True)
        recorded_at = parse_datetime(body["recorded_at"], "recorded_at") if body.get("recorded_at") else utcnow()
        reading = EnergyReading(
            classroom=room,
            power_watts=watts,
            lights_on=boolean_field(body, "lights_on", watts > 0),
            fans_on=boolean_field(body, "fans_on"),
            ac_on=boolean_field(body, "ac_on"),
            source=body.get("source", "measured"),
            recorded_at=recorded_at,
        )
        if reading.source not in ("measured", "simulated"):
            raise ServiceError("source must be measured or simulated.")
        db.session.add(reading)
        db.session.commit()
        incident = evaluate_wastage(room, app.config)
        return success(
            {"reading": reading.to_dict(), "incident_id": incident.id if incident else None}, 201
        )

    @app.post("/api/energy/simulate")
    def energy_simulate():
        body = body_object()
        classroom_id = body.get("classroom_id")
        room = (
            db.session.get(Classroom, classroom_id)
            if isinstance(classroom_id, int) and not isinstance(classroom_id, bool)
            else None
        )
        if not room:
            raise ServiceError("A valid classroom_id is required.")
        watts = valid_positive_number(body.get("power_watts"), "power_watts", allow_zero=True)
        count = body.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
            raise ServiceError("count must be an integer between 1 and 10.")
        interval = body.get("interval_seconds", 15)
        if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 300:
            raise ServiceError("interval_seconds must be an integer between 1 and 300.")
        now = utcnow()
        readings = []
        for index in range(count):
            reading = EnergyReading(
                classroom=room,
                power_watts=watts,
                lights_on=watts > 0,
                fans_on=watts > 200,
                ac_on=watts > 500,
                source="simulated",
                recorded_at=now - timedelta(seconds=interval * (count - index - 1)),
            )
            db.session.add(reading)
            readings.append(reading)
        db.session.commit()
        incident = evaluate_wastage(room, app.config)
        return success(
            {
                "readings": [reading.to_dict() for reading in readings],
                "incident_id": incident.id if incident else None,
                "incident_detected": incident is not None,
            },
            201,
        )

    @app.get("/api/energy/classroom/<int:classroom_id>")
    def energy_classroom(classroom_id):
        room = db.session.get(Classroom, classroom_id)
        if not room:
            raise ServiceError("Classroom was not found.", 404)
        readings = (
            EnergyReading.query.filter_by(classroom_id=room.id)
            .order_by(EnergyReading.recorded_at.desc())
            .limit(200)
            .all()
        )
        return success(
            {
                "classroom": room.to_dict(),
                "readings": [reading.to_dict() for reading in readings],
                "energy_kwh": round(
                    integrate_readings(
                        list(reversed(readings)), app.config["MAX_READING_GAP_SECONDS"]
                    ),
                    4,
                ),
            }
        )

    @app.get("/api/alerts")
    def alerts_list():
        status = request.args.get("status")
        query = Alert.query
        if status:
            if status not in ("open", "acknowledged", "resolved"):
                raise ServiceError("status must be open, acknowledged, or resolved.")
            query = query.filter_by(status=status)
        return success(
            [item.to_dict() for item in query.order_by(Alert.created_at.desc()).limit(200).all()]
        )

    @app.patch("/api/alerts/<int:alert_id>")
    def alerts_update(alert_id):
        alert = db.session.get(Alert, alert_id)
        if not alert:
            raise ServiceError("Alert was not found.", 404)
        body = body_object()
        status = body.get("status")
        if status not in ("acknowledged", "resolved"):
            raise ServiceError("status must be acknowledged or resolved.")
        alert.status = status
        alert.resolved_at = utcnow() if status == "resolved" else None
        if status == "resolved":
            incident = EnergyIncident.query.filter_by(alert_id=alert.id, status="active").first()
            if incident:
                incident.status = "resolved"
                incident.ended_at = utcnow()
        db.session.commit()
        return success(alert.to_dict())

    def build_report():
        start, end = get_date_range()
        query = EnergyReading.query.filter(
            EnergyReading.recorded_at >= start, EnergyReading.recorded_at <= end
        )
        room_filter = None
        if request.args.get("classroom_id"):
            try:
                room_filter = int(request.args["classroom_id"])
            except ValueError as error:
                raise ServiceError("classroom_id must be an integer.") from error
            if room_filter < 1:
                raise ServiceError("classroom_id must be a positive integer.")
            if not db.session.get(Classroom, room_filter):
                raise ServiceError("Classroom was not found.", 404)
            query = query.filter_by(classroom_id=room_filter)
        readings = query.order_by(EnergyReading.classroom_id, EnergyReading.recorded_at).all()
        by_classroom = {}
        for reading in readings:
            by_classroom.setdefault(reading.classroom_id, []).append(reading)
        energy_by_room = {}
        for room_id, room_readings in by_classroom.items():
            energy_by_room[room_id] = integrate_readings(
                room_readings, app.config["MAX_READING_GAP_SECONDS"]
            )
        measured_kwh = 0.0
        simulated_kwh = 0.0
        for room_readings in by_classroom.values():
            source_energy = integrate_readings_by_source(
                room_readings, app.config["MAX_READING_GAP_SECONDS"]
            )
            measured_kwh += source_energy["measured"]
            simulated_kwh += source_energy["simulated"]
        incident_query = EnergyIncident.query.filter(
            EnergyIncident.started_at <= end,
            db.or_(EnergyIncident.ended_at.is_(None), EnergyIncident.ended_at >= start),
        )
        if room_filter:
            incident_query = incident_query.filter_by(classroom_id=room_filter)
        incidents = incident_query.all()
        alert_query = Alert.query.filter(
            Alert.created_at >= start,
            Alert.created_at <= end,
        )
        if room_filter:
            alert_query = alert_query.filter_by(classroom_id=room_filter)
        report_alerts = alert_query.order_by(Alert.created_at.desc()).limit(200).all()
        avoidable_by_room = {}
        for incident in incidents:
            if is_confirmed_empty(incident.classroom):
                avoidable_by_room[incident.classroom_id] = (
                    avoidable_by_room.get(incident.classroom_id, 0)
                    + incident.estimated_kwh
                )
        estimated_kwh = sum(avoidable_by_room.values())
        return {
            "start": start.replace(tzinfo=timezone.utc).isoformat(),
            "end": end.replace(tzinfo=timezone.utc).isoformat(),
            "measured_kwh": round(measured_kwh, 4),
            "simulated_kwh": round(simulated_kwh, 4),
            "estimated_avoidable_kwh": round(estimated_kwh, 4),
            "potential_savings_inr": round(
                estimated_kwh * app.config["ELECTRICITY_TARIFF_INR"], 2
            ),
            "tariff_inr_per_kwh": app.config["ELECTRICITY_TARIFF_INR"],
            "classrooms": [
                {
                    "classroom_id": room.id,
                    "classroom": room.room_code,
                    "department": room.department,
                    "energy_kwh": round(energy_by_room.get(room.id, 0), 4),
                    "estimated_avoidable_kwh": round(
                        avoidable_by_room.get(room.id, 0), 4
                    ),
                    "potential_savings_inr": round(
                        avoidable_by_room.get(room.id, 0)
                        * app.config["ELECTRICITY_TARIFF_INR"],
                        2,
                    ),
                }
                for room in Classroom.query.order_by(Classroom.room_code).all()
                if not room_filter or room.id == room_filter
            ],
            "incidents": [
                {
                    "id": incident.id,
                    "classroom_id": incident.classroom_id,
                    "classroom": incident.classroom.room_code,
                    "started_at": incident.started_at.replace(tzinfo=timezone.utc).isoformat(),
                    "ended_at": incident.ended_at.replace(tzinfo=timezone.utc).isoformat()
                    if incident.ended_at
                    else None,
                    "estimated_kwh": round(incident.estimated_kwh, 4),
                    "status": incident.status,
                    "confirmed_empty": is_confirmed_empty(incident.classroom),
                }
                for incident in incidents
            ],
            "alerts": [alert.to_dict() for alert in report_alerts],
        }

    @app.get("/api/reports/energy")
    def energy_report():
        return success(build_report())

    @app.get("/api/reports/energy/export")
    def energy_report_export():
        report = build_report()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Classroom",
                "Department",
                "Energy (kWh)",
                "Estimated avoidable (kWh)",
                "Potential savings (INR)",
            ]
        )
        for item in report["classrooms"]:
            writer.writerow(
                [
                    item["classroom"],
                    item["department"],
                    item["energy_kwh"],
                    item["estimated_avoidable_kwh"],
                    item["potential_savings_inr"],
                ]
            )
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=campus-energy-report.csv"},
        )

    @app.post("/api/demo/seed")
    def demo_seed():
        created = seed_demo_data()
        return success(
            {"seeded": created, "message": "Demo data seeded." if created else "Demo data already exists."},
            201 if created else 200,
        )

    @app.post("/api/demo/reset")
    def demo_reset():
        if not app.config["ALLOW_DEMO_RESET"] or app.config.get("ENV") == "production":
            raise ServiceError("Demo reset is disabled in production.", 403)
        db.session.remove()
        db.drop_all()
        db.create_all()
        created = seed_demo_data()
        return success({"reset": True, "seeded": created})

    @app.post("/api/demo/simulate-empty-room-wastage")
    def simulate_empty_wastage():
        body = body_object()
        if body.get("confirm_empty") is not True:
            raise ServiceError("Confirm that the room is empty before running this demo.")
        classroom_id = body.get("classroom_id")
        room = (
            db.session.get(Classroom, classroom_id)
            if isinstance(classroom_id, int) and not isinstance(classroom_id, bool)
            else None
        )
        if not room:
            raise ServiceError("A valid classroom_id is required.")
        if any(session.status == "active" for session in room.sessions):
            raise ServiceError("Complete the active class session before confirming the room empty.", 409)
        room.empty_confirmed = True
        watts = valid_positive_number(body.get("power_watts", 320), "power_watts")
        duration = max(app.config["WASTE_DURATION_SECONDS"], 2)
        now = utcnow()
        number_of_readings = 4
        interval = max(
            1, (duration + number_of_readings - 2) // (number_of_readings - 1)
        )
        readings = []
        for index in range(number_of_readings):
            reading = EnergyReading(
                classroom=room,
                power_watts=watts,
                lights_on=True,
                fans_on=watts > 200,
                ac_on=watts > 500,
                source="simulated",
                recorded_at=now - timedelta(seconds=interval * (number_of_readings - index - 1)),
            )
            db.session.add(reading)
            readings.append(reading)
        db.session.commit()
        incident = evaluate_wastage(room, app.config)
        return success(
            {
                "classroom": room.room_code,
                "confirmed_empty": is_confirmed_empty(room),
                "readings_added": len(readings),
                "incident_detected": incident is not None,
                "incident_id": incident.id if incident else None,
                "estimated_kwh": round(incident.estimated_kwh, 4) if incident else 0,
                "potential_savings_inr": round(
                    incident.estimated_kwh * app.config["ELECTRICITY_TARIFF_INR"], 2
                )
                if incident
                else 0,
            },
            201,
        )

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        seed_demo_data()
    app.run(host="127.0.0.1", port=5000, debug=False)

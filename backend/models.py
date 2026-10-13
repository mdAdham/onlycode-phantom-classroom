from datetime import datetime, timezone

from sqlalchemy import Index, UniqueConstraint

from extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    attendance = db.relationship("Attendance", back_populates="student")

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "name": self.name,
            "department": self.department,
            "is_active": self.is_active,
        }


class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    department = db.Column(db.String(80), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    responsible_staff = db.Column(db.String(120), nullable=False)
    empty_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    sessions = db.relationship("ClassSession", back_populates="classroom")
    readings = db.relationship("EnergyReading", back_populates="classroom")
    alerts = db.relationship("Alert", back_populates="classroom")

    def to_dict(self):
        active = next((s for s in self.sessions if s.status == "active"), None)
        latest = max(self.readings, key=lambda r: r.recorded_at, default=None)
        attendance_count = (
            sum(record.status == "verified" for record in active.attendance)
            if active
            else 0
        )
        latest_session = max(
            self.sessions, key=lambda session: session.start_time, default=None
        )
        if active:
            occupancy_status = "Occupied" if attendance_count else "Awaiting occupancy confirmation"
        elif self.empty_confirmed or (
            latest_session and latest_session.status == "completed"
        ):
            occupancy_status = "Confirmed empty"
        else:
            occupancy_status = "No active session"
        current_alert = next(
            (a for a in reversed(self.alerts) if a.status in ("open", "acknowledged")),
            None,
        )
        return {
            "id": self.id,
            "room_code": self.room_code,
            "department": self.department,
            "capacity": self.capacity,
            "responsible_staff": self.responsible_staff,
            "occupancy": attendance_count,
            "occupancy_status": occupancy_status,
            "session_status": active.status if active else "none",
            "power_watts": latest.power_watts if latest else 0,
            "lights_on": latest.lights_on if latest else False,
            "fans_on": latest.fans_on if latest else False,
            "ac_on": latest.ac_on if latest else False,
            "wastage_status": "Alert" if current_alert else "Normal",
        }


class ClassSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=False, index=True)
    subject = db.Column(db.String(120), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="scheduled", index=True)
    qr_token_hash = db.Column(db.String(64))
    qr_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    classroom = db.relationship("Classroom", back_populates="sessions")
    attendance = db.relationship("Attendance", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "uq_active_session_classroom",
            "classroom_id",
            unique=True,
            sqlite_where=(status == "active"),
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "classroom_id": self.classroom_id,
            "classroom": self.classroom.room_code,
            "subject": self.subject,
            "start_time": self.start_time.replace(tzinfo=timezone.utc).isoformat(),
            "end_time": self.end_time.replace(tzinfo=timezone.utc).isoformat(),
            "status": self.status,
            "attendance_count": sum(record.status == "verified" for record in self.attendance),
        }


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("class_session.id"), nullable=False)
    marked_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    method = db.Column(db.String(20), nullable=False, default="manual")
    status = db.Column(db.String(20), nullable=False, default="verified")
    student = db.relationship("Student", back_populates="attendance")
    session = db.relationship("ClassSession", back_populates="attendance")

    __table_args__ = (UniqueConstraint("student_id", "session_id", name="uq_student_session_attendance"),)

    def to_dict(self):
        return {
            "id": self.id,
            "student": self.student.to_dict(),
            "session_id": self.session_id,
            "session": self.session.subject,
            "classroom": self.session.classroom.room_code,
            "marked_at": self.marked_at.replace(tzinfo=timezone.utc).isoformat(),
            "method": self.method,
            "status": self.status,
        }


class EnergyReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=False, index=True)
    power_watts = db.Column(db.Float, nullable=False)
    lights_on = db.Column(db.Boolean, nullable=False, default=False)
    fans_on = db.Column(db.Boolean, nullable=False, default=False)
    ac_on = db.Column(db.Boolean, nullable=False, default=False)
    source = db.Column(db.String(20), nullable=False, default="simulated")
    recorded_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    classroom = db.relationship("Classroom", back_populates="readings")

    def to_dict(self):
        return {
            "id": self.id,
            "classroom_id": self.classroom_id,
            "classroom": self.classroom.room_code,
            "power_watts": self.power_watts,
            "lights_on": self.lights_on,
            "fans_on": self.fans_on,
            "ac_on": self.ac_on,
            "source": self.source,
            "recorded_at": self.recorded_at.replace(tzinfo=timezone.utc).isoformat(),
        }


class EnergyIncident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime)
    peak_power_watts = db.Column(db.Float, nullable=False)
    estimated_kwh = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    alert_id = db.Column(db.Integer, db.ForeignKey("alert.id"))
    classroom = db.relationship("Classroom")
    alert = db.relationship("Alert", foreign_keys=[alert_id])

    __table_args__ = (
        Index(
            "uq_active_incident_per_classroom",
            "classroom_id",
            unique=True,
            sqlite_where=(status == "active"),
        ),
    )


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"), nullable=False, index=True)
    type = db.Column(db.String(60), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    recommended_action = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    detected_power_watts = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    resolved_at = db.Column(db.DateTime)
    classroom = db.relationship("Classroom", back_populates="alerts")

    def to_dict(self):
        classroom_state = self.classroom.to_dict()
        active_session = next(
            (session for session in self.classroom.sessions if session.status == "active"),
            None,
        )
        latest_session = max(
            self.classroom.sessions, key=lambda session: session.start_time, default=None
        )
        return {
            "id": self.id,
            "classroom_id": self.classroom_id,
            "classroom": self.classroom.room_code,
            "department": self.classroom.department,
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "recommended_action": self.recommended_action,
            "status": self.status,
            "detected_power_watts": self.detected_power_watts,
            "occupancy": classroom_state["occupancy"],
            "occupancy_status": classroom_state["occupancy_status"],
            "session_status": (
                active_session.status
                if active_session
                else latest_session.status if latest_session else "none"
            ),
            "created_at": self.created_at.replace(tzinfo=timezone.utc).isoformat(),
            "resolved_at": (
                self.resolved_at.replace(tzinfo=timezone.utc).isoformat()
                if self.resolved_at
                else None
            ),
        }

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS


app = Flask(__name__)

# SQLite configuration - stores DB in local file appointments.db
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///appointments.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
_cors = CORS(app, resources={r"/*": {"origins": "*"}})


class Patient(db.Model):  # type: ignore[misc]
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(50))
    date_of_birth = db.Column(db.Date)
    medical_notes = db.Column(db.Text)

    # Backref appointments will be available via patient.appointments


class Appointment(db.Model):  # type: ignore[misc]
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    patient = db.relationship("Patient", backref=db.backref("appointments", lazy=True))
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    source = db.Column(db.String(100), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        # Include patient fields for compatibility with existing frontend
        patient_name = self.patient.full_name if self.patient else None
        patient_phone = self.patient.phone_number if self.patient else None
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": patient_name,
            "patient_phone": patient_phone,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "source": self.source,
        }


with app.app_context():
    db.create_all()


@app.get("/")
def index() -> Any:
    return render_template("index.html")


@app.get("/health")
def health() -> Any:
    return {"status": "ok"}


@app.get("/appointments")
def list_appointments() -> Any:
    appointments = Appointment.query.order_by(Appointment.start_time.asc()).all()
    return jsonify([a.to_dict() for a in appointments])


@app.post("/appointments")
def create_appointment() -> Any:
    data = request.get_json(silent=True) or {}

    # Accept either patient_id directly or legacy patient_name/phone
    required_keys = ["start_time", "end_time", "source"]
    legacy_patient_keys = ["patient_name", "patient_phone"]

    missing = [key for key in required_keys if key not in data]
    if missing:
        return {"error": f"Missing fields: {', '.join(missing)}"}, 400

    try:
        start_dt = _parse_iso_datetime(str(data["start_time"]))
        end_dt = _parse_iso_datetime(str(data["end_time"]))
    except ValueError as exc:
        return {"error": str(exc)}, 400

    if end_dt <= start_dt:
        return {"error": "end_time must be after start_time"}, 400

    patient_id: Optional[int] = data.get("patient_id")
    if patient_id is None:
        # Legacy path: create or reuse a patient based on provided name/phone
        if not all(k in data for k in legacy_patient_keys):
            return {"error": "Provide patient_id or patient_name and patient_phone"}, 400
        full_name = str(data["patient_name"]).strip()
        phone = str(data["patient_phone"]).strip()
        existing = (
            Patient.query.filter_by(full_name=full_name, phone_number=phone).first()
        )
        if existing is None:
            existing = Patient(full_name=full_name, phone_number=phone)
            db.session.add(existing)
            db.session.flush()  # obtain id
        patient_id = existing.id

    # Ensure patient exists
    patient = db.session.get(Patient, int(patient_id))
    if patient is None:
        return {"error": "Invalid patient_id"}, 400

    appointment = Appointment(
        patient_id=patient.id,
        start_time=start_dt,
        end_time=end_dt,
        source=str(data["source"]),
    )

    db.session.add(appointment)
    db.session.commit()

    return appointment.to_dict(), 201


def _parse_iso_datetime(value: str) -> datetime:
    # Accept common ISO 8601 formats like "2025-10-06T14:30:00" or with Z/offset
    try:
        # fromisoformat handles "YYYY-MM-DDTHH:MM:SS[.ffffff][+HH:MM]"
        # Replace trailing 'Z' with '+00:00' for UTC
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except Exception as e:  # noqa: BLE001
        raise ValueError(
            "Invalid datetime format. Use ISO 8601, e.g. 2025-10-06T14:30:00"
        ) from e


@app.delete("/appointments/<int:appointment_id>")
def delete_appointment(appointment_id: int) -> Any:
    appointment = db.session.get(Appointment, appointment_id)
    if appointment is None:
        return {"error": "Appointment not found"}, 404
    db.session.delete(appointment)
    db.session.commit()
    return {"status": "deleted", "id": appointment_id}


@app.get("/api/appointments")
def api_appointments_by_date() -> Any:
    """Return appointments for a given date as start/end pairs.

    Query param: date=YYYY-MM-DD
    """
    date_str = request.args.get("date", type=str)
    if not date_str:
        return {"error": "Missing required 'date' query param (YYYY-MM-DD)"}, 400
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

    day_start = datetime.combine(day, datetime.min.time())
    day_end = datetime.combine(day, datetime.max.time())

    # Appointments whose start_time falls on the given date
    appts = (
        Appointment.query
        .filter(Appointment.start_time >= day_start, Appointment.start_time <= day_end)
        .order_by(Appointment.start_time.asc())
        .all()
    )
    return jsonify([
        {"start_time": a.start_time.isoformat(), "end_time": a.end_time.isoformat()} for a in appts
    ])


@app.post("/api/appointments")
def api_create_appointment() -> Any:
    data = request.get_json(silent=True) or {}

    for key in ["patient_id", "start_time", "end_time"]:
        if key not in data:
            return {"error": f"Missing field: {key}"}, 400

    patient = db.session.get(Patient, int(data["patient_id"]))
    if patient is None:
        return {"error": "Invalid patient_id"}, 400

    try:
        start_dt = _parse_iso_datetime(str(data["start_time"]))
        end_dt = _parse_iso_datetime(str(data["end_time"]))
    except ValueError as exc:
        return {"error": str(exc)}, 400

    if end_dt <= start_dt:
        return {"error": "end_time must be after start_time"}, 400

    appt = Appointment(
        patient_id=patient.id,
        start_time=start_dt,
        end_time=end_dt,
        source=str(data.get("source", "api")),
    )
    db.session.add(appt)
    db.session.commit()

    return {"status": "created", "id": appt.id}, 201

# if __name__ == "__main__":
#     app.run(host='0.0.0.0', debug=True)



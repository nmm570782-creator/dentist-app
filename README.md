## Flask Appointments (SQLite)

Minimal Flask API with an `Appointment` model stored in SQLite.

### Requirements
- Python 3.10+
- Windows PowerShell or any shell

### Setup
```bash
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

### Run
```bash
python app.py
```

The server listens on `http://127.0.0.1:5000`.

### Endpoints
- `GET /appointments` — list all appointments
- `POST /appointments` — create an appointment

Example `POST` body (ISO 8601 datetimes):
```json
{
  "patient_name": "John Doe",
  "patient_phone": "+1-555-0100",
  "start_time": "2025-10-06T14:30:00",
  "end_time": "2025-10-06T15:00:00",
  "source": "web"
}
```

The SQLite file `appointments.db` will be created on first run in the project folder.



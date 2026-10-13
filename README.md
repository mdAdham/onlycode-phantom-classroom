# Smart Campus Energy

Smart Campus Energy is a demo-ready campus energy dashboard that connects verified class-session attendance with classroom power readings. It flags sustained power use only after a room has been confirmed empty and estimates potentially avoidable energy and cost.

This is a hackathon MVP. Sensor readings are simulated unless an API client explicitly submits a reading as measured. Estimated savings are not verified savings, and QR attendance is not proof of physical presence.

## Features

- Campus dashboard with classrooms, registered students, active-session attendance, power, active alerts, and estimated avoidable energy.
- Attendance marking using registered student IDs and short-lived, session-specific QR tokens; backend validation and a database uniqueness constraint prevent duplicate marks.
- Classroom directory with occupancy, appliance states, staff assignment, energy readings, and class-session details.
- Energy monitoring with simulated readings and a confirmed-empty-room wastage demonstration.
- Rule-based incident and alert creation, acknowledgement, resolution, and active-alert de-duplication.
- Energy reports with a date range, classroom comparison, incident history, rupee tariff estimates, and CSV export.
- Eight fictional classrooms, 48 fictional students, sessions, attendance, appliance readings, and active/resolved alerts for the demo.
- Responsive React interface with QR display and optional camera scanning.

## Architecture and technology

- **Frontend:** React 19, Vite, React Router, Recharts, Lucide React, `qrcode.react`, and `html5-qrcode`.
- **Backend:** Python, Flask, Flask-SQLAlchemy, Flask-CORS, and SQLite.
- **Business logic:** [`backend/services.py`](./backend/services.py) validates attendance, hashes and expires QR tokens, integrates energy readings, evaluates wastage incidents, and seeds demo data.
- **Persistence and constraints:** [`backend/models.py`](./backend/models.py) defines students, classrooms, sessions, attendance, readings, incidents, and alerts. Attendance is unique per student and session; SQLite also prevents overlapping active sessions per classroom.
- **Frontend API client:** [`frontend/src/services/api.js`](./frontend/src/services/api.js) centralizes JSON requests and CSV download handling.

## Folder structure

```text
backend/
  app.py                 Flask application and REST routes
  config.py              Environment-based settings
  extensions.py          SQLAlchemy instance
  models.py              Database models
  services.py            Attendance, energy, incident, and seed logic
  tests/test_api.py      Isolated API and business-logic tests
  requirements.txt
frontend/
  src/
    components/          Lazy-loaded charts and QR camera scanner
    services/api.js      Centralized API client
    App.jsx              Navigation, pages, and workflows
    App.css
    index.css
```

## Prerequisites

- Python 3.10 or newer (tested here with Python 3.14).
- Node.js 20 or newer and npm.
- Windows PowerShell commands below assume the terminal is at the project root.

## Start the backend

In a PowerShell terminal:

```powershell
Set-Location .\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

The first `python app.py` creates the SQLite schema and seeds fictional demo data if the database is empty. The API listens on `http://127.0.0.1:5000`.

The demo can also be seeded explicitly without duplicating records:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/demo/seed
```

The data file is `backend\campus_energy.db`. To rebuild the demo through the API, use the UI's **Reset demo** action or:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/demo/reset
```

Demo reset is enabled by default in development and disabled when `FLASK_ENV=production` unless explicitly overridden. This MVP has no authentication; do not expose the demo reset or other staff workflows to an untrusted network.

### Backend configuration

Use `backend\.env.example` as a reference; Python does not automatically load `.env` files in this MVP. Set values in the PowerShell process before starting Flask, or configure them in your terminal profile:

```powershell
$env:ENERGY_THRESHOLD_WATTS = "50"
$env:WASTE_DURATION_SECONDS = "30"
$env:ELECTRICITY_TARIFF_INR = "8"
$env:MAX_READING_GAP_SECONDS = "900"
```

These are illustrative demo settings, not universal energy standards. `DATABASE_URL` can override the default SQLite path. Keep `SECRET_KEY` private in a deployment.

## Start the frontend

Open a second PowerShell terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend calls `http://127.0.0.1:5000/api` by default. To use another API base, copy `frontend\.env.example` to `frontend\.env.local`, edit `VITE_API_URL`, then restart Vite. Flask CORS permits the default Vite localhost origins.

## API overview

JSON endpoints use `{ "data": ..., "error": null }` on success and a meaningful `{ "data": null, "error": "..." }` on API errors.

| Area | Endpoints |
| --- | --- |
| Health and dashboard | `GET /api/health`, `GET /api/dashboard`, `GET /api/dashboard/energy-trend` |
| Students | `GET /api/students`, `POST /api/students`, `GET /api/students/<id>` |
| Classrooms | `GET /api/classrooms`, `POST /api/classrooms`, `GET /api/classrooms/<id>` |
| Class sessions | `GET /api/sessions`, `POST /api/sessions`, `PATCH /api/sessions/<id>`, `POST /api/sessions/<id>/qr` |
| Attendance | `POST /api/attendance/mark`, `GET /api/attendance`, `GET /api/attendance/session/<session_id>` |
| Energy | `GET /api/energy/readings`, `POST /api/energy/readings`, `POST /api/energy/simulate`, `GET /api/energy/classroom/<classroom_id>` |
| Alerts | `GET /api/alerts`, `PATCH /api/alerts/<id>` |
| Reports | `GET /api/reports/energy`, `GET /api/reports/energy/export` |
| Demo | `POST /api/demo/seed`, `POST /api/demo/reset`, `POST /api/demo/simulate-empty-room-wastage` |

For date-range endpoints, optional `start` and `end` query parameters accept ISO-8601 timestamps. The date range is validated and capped at 366 days.

## Tests and frontend checks

Run backend tests against an isolated in-memory SQLite database:

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest -q
```

Run frontend lint and production build:

```powershell
Set-Location .\frontend
npm run lint
npm run build
```

## Live demo walkthrough

1. Start the backend and frontend; open the overview dashboard and review the eight rooms, live sample power, active alert, and estimated savings.
2. Open **Attendance** and select an active session. Generate its QR token; use the matching registered student ID (for example, `STU-009`) and mark the student present. Generate the QR before marking attendance. The duplicate mark is rejected by the API.
3. The camera scanner is optional and requires browser camera permission on `localhost` or HTTPS. If unavailable, use the manual student-ID input.
4. On **Energy monitoring**, choose a classroom without an active session, confirm the room is empty, and run **Simulate empty-room wastage**. The API adds a short sequence of above-threshold simulated readings and evaluates the configured duration rule.
5. Open **Alerts** to acknowledge or resolve the incident, and **Reports** to see its estimated kWh and potential rupee savings. The live demo works without physical sensors.
6. To show incident clearing, add a zero-watt simulated reading for that room using the normal reading control. The underlying active incident and alert are closed when the condition clears.
7. Use **Reset demo** to restore the original sample state before another walkthrough.

## Occupancy, energy, and safety limitations

- Zero attendance during an active class is shown as **Awaiting occupancy confirmation**; it is not treated as an empty room. Empty-room detection requires a completed session or an explicit room-empty confirmation. The demo confirmation is not authenticated; production use needs an authorized staff workflow.
- QR tokens are random, SHA-256 hashed at rest, session-specific, and expire after 15 minutes. Duplicate marks are prevented transactionally. A QR token alone cannot prove that a student is physically present, prevent collusion, or replace identity checks.
- Energy consumption is integrated from adjacent power readings using `kWh = average watts × elapsed hours / 1000`. Missing or excessively distant readings are excluded. A recommended action or alert is not proof that energy was saved.
- The prototype uses simulated readings and an illustrative configurable threshold/tariff. It does not control lights, fans, or AC, connect to smart meters, or verify real billing savings.
- There is no authentication or authorization layer in this hackathon MVP. Add staff/student authentication, audit logging, privacy retention rules, and deployment controls before production.

## Future improvements

- Integrate authenticated IoT smart meters and validate meter calibration and data gaps.
- Connect appliance switching only through authorized, safety-reviewed hardware and staff confirmation.
- Add campus identity-provider authentication, roles, audit history, and privacy-conscious retention.
- Calibrate energy thresholds, tariffs, occupancy policy, and incident durations with facilities teams.

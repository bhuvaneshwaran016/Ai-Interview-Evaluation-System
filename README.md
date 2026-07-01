# AI Interview Evaluation System

A FastAPI-based platform for conducting and evaluating recorded video interviews.
It handles candidate sign-up/resume upload, video interview recording, transcription
(Faster-Whisper), facial expression analysis (DeepFace/Mediapipe), and stores
interview videos via Cloudinary with a PostgreSQL backend.

## Project Structure

```
Ai-Interview-Evaluation-System/
├── main.py                     # FastAPI app entry point (API routes, DB models)
├── upload_server.py            # Standalone upload helper server
├── requirements.txt            # Python dependencies
├── .env.example                # Template for required environment variables
├── .gitignore
│
├── frontpage.html              # Landing page
├── student sign.html           # Candidate sign-up page
├── attach_resume.html          # Resume upload page
├── interview.html              # Interview recording page
├── company.html                # Company/recruiter dashboard
│
├── audio_enhancement.py        # Audio cleanup before transcription
├── face_detection.py           # Facial expression detection
├── transcribe_video.py         # Faster-Whisper transcription
├── process_transcriptions.py   # Batch processing of transcriptions
├── simple_transcribe_workflow.py
├── export_transcriptions.py    # Export transcriptions to CSV
├── update_expressions.py       # Update stored expression results
├── reprocess_videos.py
├── reprocess_all_videos.py
├── reprocess_improved.py
├── reset_failed_expressions.py
├── download_weights.py         # Download model weights (DeepFace/Whisper)
├── migrate_db.py                # DB schema migration helper
├── migrate_interview_video.py
├── kill_pg_locks.py             # Utility to clear stuck Postgres locks
├── lightweight_start.py         # Lightweight startup mode
├── start_fast.py                # Fast startup mode
├── run_with_waitress.py         # Run app with Waitress (Windows WSGI server)
├── run_server.bat               # Windows batch launcher
└── run_server.ps1               # PowerShell launcher
```

> Debug/inspection one-off scripts (`check_*.py`, `inspect_*.py`, `test_*.py`),
> sample data (`*.csv`, `*.pdf`, `*.db`), the bundled Python runtime
> (`DLLs/`, `Lib/`, `Scripts/`, `Tools/`, `Doc/`, `include/`, `libs/`, `tcl/`,
> `python.exe`, `*.dll`), and virtual environments (`venv/`, `.venv/`,
> `deepface_env/`) from the original working folder are intentionally **not**
> included — they aren't needed to run the app and bloat the repo.

## Requirements

- Python 3.10/3.11
- PostgreSQL database
- A Cloudinary account (for video storage)
- ffmpeg available on PATH (used by faster-whisper / audio processing)

## Setup

1. **Clone the repo and enter the folder**
   ```bash
   git clone <your-repo-url>
   cd Ai-Interview-Evaluation-System
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   Copy `.env.example` to `.env` and fill in your real database and Cloudinary
   credentials:
   ```bash
   cp .env.example .env
   ```

5. **Create the PostgreSQL database**

   Log into Postgres:
   ```bash
   psql -U postgres
   ```
   Then inside the `psql` prompt, set a password and create the database
   (use the same password in your `.env` file):
   ```sql
   ALTER USER postgres WITH PASSWORD 'YourNewStrongPassword';
   CREATE DATABASE interview_db;
   \q
   ```
   > Don't have PostgreSQL installed yet?
   > - **Windows:** install from [postgresql.org](https://www.postgresql.org/download/) (set the password during setup)
   > - **macOS:** `brew install postgresql@16 && brew services start postgresql@16`
   > - **Linux (Ubuntu/Debian):** `sudo apt install postgresql`, then `sudo -u postgres psql`

   App tables are created automatically on first run — this manual step is
   only needed to create the database itself.

6. **Run the server**
   ```bash
   python main.py
   ```
   or, on Windows, double-click / run:
   ```bash
   run_server.bat
   ```
   uvicorn main:app --host 0.0.0.0 --port 8000

   ```like this command is used for run the project 

   By default FastAPI/uvicorn will start the app — check the printed startup
   logs for the local URL (typically `http://127.0.0.1:8000`).

## ⚠️ Security Note

`main.py` currently contains **hardcoded Cloudinary and database credentials**
as fallback default values. Before pushing this repository publicly, replace
those hardcoded values with `os.getenv(...)` calls only (no hardcoded
fallback secrets), and make sure your real `.env` file is never committed
(it's already excluded via `.gitignore`).

## Notes

- Model weights for Whisper/DeepFace are downloaded on first run or via
  `download_weights.py`.
- Use `migrate_db.py` if you need to update an existing database schema.



## use uv 
STEP 1)
   Push From GitHub we need to use uv 
STEP 2)
   Commants 
   1) Open Terminal in Vs code For this Project
   2) uv init
   3) uv venv
   4) .venv\Scripts\activate
   5) uv add requests
   6) uv add -r requirements.txt

STEP 3)
   Use Open Server To Run This Project
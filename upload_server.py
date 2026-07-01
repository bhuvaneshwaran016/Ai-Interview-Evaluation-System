from dotenv import load_dotenv
load_dotenv()

#!/usr/bin/env python3
"""
Simple FastAPI server for video uploads - bypasses main.py import issues
"""
import os
import time
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras

# Create app
app = FastAPI(title="Interview Video Upload Server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
DB_CONFIG = {
    "host": "localhost",
    "database": "interview_db",
    "user": "postgres",
    "password": os.getenv("DB_PASSWORD"),
    "port": 5432
}

VIDEOS_DIR = os.path.join(os.getcwd(), "videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok", "message": "Upload server ready"}

@app.post("/upload-video")
async def upload_video(
    email: str = Form(...),
    session_id: str = Form(...),
    question_index: int = Form(...),
    question_text: str = Form(default=""),
    file: UploadFile = File(...)
):
    """Save video locally and store in database"""
    try:
        print(f"📤 Upload received for {email}, question {question_index}")
        
        # Get candidate ID
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM candidates WHERE email = %s", (email,))
        result = cur.fetchone()
        
        if not result:
            conn.close()
            print(f"❌ Candidate not found: {email}")
            raise HTTPException(status_code=404, detail="Candidate not found")
        
        candidate_id = result[0]
        
        # Save video file
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        video_filename = f"{candidate_id}_{session_id}_q{question_index}_{int(time.time())}.webm"
        video_path = os.path.join(VIDEOS_DIR, video_filename)
        
        content = await file.read()
        with open(video_path, "wb") as f:
            f.write(content)
        
        print(f"✅ Video saved: {video_path} ({file_size} bytes)")
        
        # Save to database
        cur.execute("""
            INSERT INTO interview_video 
            (candidate_id, session_id, question_index, question_text, video_url, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            candidate_id,
            session_id,
            question_index,
            question_text,
            video_path,
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"✅ Video recorded in database")
        
        return {
            "message": "Video uploaded successfully",
            "video_id": cur.lastrowid if hasattr(cur, 'lastrowid') else 0,
            "video_path": video_path,
            "question_index": question_index,
            "candidate_id": candidate_id
        }
        
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("🚀 INTERVIEW VIDEO UPLOAD SERVER")
    print("="*70)
    print("Server: http://127.0.0.1:8000")
    print("Health: http://127.0.0.1:8000/health")
    print("Docs: http://127.0.0.1:8000/docs")
    print("="*70 + "\n")
    
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

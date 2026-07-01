from dotenv import load_dotenv
load_dotenv()

import sys
import os
import cv2
import tempfile
import requests
import subprocess
import imageio_ffmpeg
import shutil
from faster_whisper import WhisperModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import InterviewVideo, SessionLocal  # Import only what we need

# Load Faster-Whisper model
whisper_model = WhisperModel("small", device="auto", compute_type="int8")

def reprocess_video(video_id):
    db = SessionLocal()
    try:
        video = db.query(InterviewVideo).filter(InterviewVideo.id == video_id).first()
        if not video or not video.video_url:
            return

        print(f"Reprocessing video {video_id}...")

        # Download video
        tmp_path = None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            resp = requests.get(video.video_url, stream=True)
            if resp.status_code == 200:
                for chunk in resp.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name

        try:
            # Extract audio
            audio_tmp_path = tmp_path.replace(".webm", ".wav")
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

            ffmpeg_cmd = [
                ffmpeg_exe,
                '-i', tmp_path,
                '-vn',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-y',
                audio_tmp_path
            ]

            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=60)

            # Transcribe
            segments, info = whisper_model.transcribe(audio_tmp_path, language='en')
            transcription_text = "".join([segment.text for segment in segments]).strip()

            # Clean text
            import re
            transcription_text = re.sub(r'\s+', ' ', transcription_text)
            transcription_text = ''.join(c for c in transcription_text if c.isprintable())
            transcription_text = transcription_text.strip()

            if transcription_text and len(transcription_text) >= 5:
                video.transcription = transcription_text
                print(f"✅ Updated transcription: {transcription_text[:50]}...")
            else:
                video.transcription = "No clear speech detected"

            # Skip expression analysis and AI feedback
            video.expression_analysis = "skipped"
            video.ai_feedback = "skipped"
            print(f"✅ Skipped face detection and AI evaluation for video {video_id}")

            db.commit()
            print(f"✅ Reprocessed video {video_id} (transcription only)")

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            audio_path = tmp_path.replace(".webm", ".wav")
            if os.path.exists(audio_path):
                os.remove(audio_path)

    except Exception as e:
        print(f"❌ Error reprocessing video {video_id}: {e}")
    finally:
        db.close()

# Get videos that need reprocessing
import psycopg2
conn = psycopg2.connect(host='localhost', database='interview_db', user='postgres', password=os.getenv('DB_PASSWORD'), port=5432)
cur = conn.cursor()
cur.execute("SELECT id FROM interview_video WHERE transcription IS NOT NULL AND (expression_analysis IS NULL OR expression_analysis = 'Analysis failed')")
video_ids = [row[0] for row in cur.fetchall()]
conn.close()

print(f"Found {len(video_ids)} videos to reprocess")

for video_id in video_ids:
    reprocess_video(video_id)
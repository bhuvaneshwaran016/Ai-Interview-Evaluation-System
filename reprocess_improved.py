import sys
import os
import cv2
import tempfile
import requests
import subprocess
import imageio_ffmpeg
import shutil
from faster_whisper import WhisperModel
import re
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship
from dotenv import load_dotenv

load_dotenv()

# Database setup (copied from main.py)
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class InterviewVideo(Base):
    __tablename__ = "interview_video"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=False)
    question_index = Column(Integer, nullable=False)
    question_text = Column(String)
    video_url = Column(String, nullable=False)
    public_id = Column(String)
    transcription = Column(String)
    expression_analysis = Column(String)
    ai_feedback = Column(String)
    created_at = Column(String)

# Load Faster-Whisper model
whisper_model = WhisperModel("medium", device="auto", compute_type="int8")

def reprocess_video(video_id):
    db = SessionLocal()
    try:
        video = db.query(InterviewVideo).filter(InterviewVideo.id == video_id).first()
        if not video or not video.video_url:
            return

        print(f"🔄 Reprocessing video {video_id}...")

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

            audio_available = False
            try:
                subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=60)
                print(f"✅ Audio extracted successfully")

                # Check if audio file has content
                if os.path.exists(audio_tmp_path) and os.path.getsize(audio_tmp_path) > 1000:
                    print(f"✅ Audio file size: {os.path.getsize(audio_tmp_path)} bytes")
                    audio_available = True
                else:
                    print(f"⚠️ Audio file too small, using video file")
                    audio_tmp_path = tmp_path

            except subprocess.CalledProcessError as e:
                print(f"⚠️ FFmpeg failed, using video file")
                audio_tmp_path = tmp_path

            # Transcribe with improved model
            print(f"🎙️ Transcribing audio file: {os.path.basename(audio_tmp_path)}")
            segments, info = whisper_model.transcribe(audio_tmp_path, language='en')
            transcription_text = "".join([segment.text for segment in segments]).strip()

            # Clean up transcription text
            transcription_text = re.sub(r'\s+', ' ', transcription_text)
            transcription_text = ''.join(c for c in transcription_text if c.isprintable() or c in '.,!?')
            transcription_text = transcription_text.strip()

            # Check for suspicious content
            if transcription_text:
                suspicious_patterns = [
                    r'thanks for watching', r'subscribe', r'like and subscribe',
                    r'follow me', r'check out', r'visit my', r'buy now',
                    r'music by', r'background music', r'copyright'
                ]

                is_suspicious = any(re.search(pattern, transcription_text.lower()) for pattern in suspicious_patterns)

                if is_suspicious:
                    print(f"⚠️ Suspicious transcription detected")
                    transcription_text = "Transcription may contain unrelated audio content"

            if transcription_text and len(transcription_text) >= 5:
                video.transcription = transcription_text
                print(f"✅ Updated transcription: {transcription_text[:50]}...")
            else:
                video.transcription = "No clear speech detected"

            # Skip face detection and AI evaluation
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
cur.execute("SELECT id FROM interview_video WHERE transcription IS NOT NULL AND (expression_analysis IS NULL OR expression_analysis LIKE 'No face%' OR expression_analysis LIKE 'Face detected%') ORDER BY id DESC")
video_ids = [row[0] for row in cur.fetchall()]
conn.close()

print(f"Found {len(video_ids)} videos to reprocess")

for video_id in video_ids:
    reprocess_video(video_id)

print("Reprocessing complete!")
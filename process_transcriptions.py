#!/usr/bin/env python3
"""
Script to process untranscribed videos and extract audio to text
"""
import os
import sys
import tempfile
import requests
import subprocess
import re
from sqlalchemy import create_engine, Column, Integer, String, inspect, text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Model
Base = declarative_base()

class InterviewVideo(Base):
    __tablename__ = "interview_video"
    id = Column(Integer, primary_key=True, index=True)
    video_url = Column(String, nullable=False)
    transcription = Column(String)

def download_video_to_temp_file(url_or_path):
    """Download video from URL or copy local file to temp"""
    if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
        # It's a URL
        resp = requests.get(url_or_path, stream=True, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name
    else:
        # It's a local file path
        if os.path.exists(url_or_path):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
                with open(url_or_path, 'rb') as src:
                    tmp.write(src.read())
                return tmp.name
        else:
            raise FileNotFoundError(f"Local file not found: {url_or_path}")

def extract_audio(video_path, audio_path):
    """Extract audio from video using ffmpeg"""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe,
        '-i', video_path,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        '-y',
        audio_path
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=90)

def transcribe_audio(audio_path):
    """Transcribe audio using Faster-Whisper"""
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="auto", compute_type="int8")  # Use tiny model for faster processing
    segments, info = model.transcribe(audio_path, language='en')
    transcription_text = "".join([segment.text for segment in segments]).strip()
    transcription_text = re.sub(r'\s+', ' ', transcription_text)
    transcription_text = ''.join(c for c in transcription_text if c.isprintable() or c in '.,!?')
    return transcription_text.strip()

def process_video(video_id, video_url):
    """Process a single video for transcription"""
    print(f"Processing video {video_id}...")

    tmp_path = None
    audio_path = None

    try:
        # Download video
        tmp_path = download_video_to_temp_file(video_url)
        print(f"Downloaded to {tmp_path}")

        # Extract audio
        audio_path = os.path.splitext(tmp_path)[0] + ".wav"
        extract_audio(tmp_path, audio_path)
        print(f"Audio extracted to {audio_path}")

        # Transcribe
        transcription = transcribe_audio(audio_path)
        if transcription and len(transcription) >= 2:
            print(f"Transcription: {transcription[:100]}...")
            return transcription
        else:
            return "No clear speech detected"

    except Exception as e:
        print(f"Error processing video {video_id}: {e}")
        return f"Transcription failed: {e}"
    finally:
        # Cleanup
        for path in [tmp_path, audio_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

def main():
    db = SessionLocal()
    try:
        # Get videos without transcription
        videos = db.query(InterviewVideo).filter(
            (InterviewVideo.transcription == None) |
            (InterviewVideo.transcription == "No clear speech detected") |
            (InterviewVideo.transcription.startswith("Transcription failed"))
        ).all()

        if not videos:
            print("No unprocessed videos found.")
            return

        print(f"Found {len(videos)} videos to process.")

        for video in videos:
            transcription = process_video(video.id, video.video_url)
            video.transcription = transcription
            db.commit()
            print(f"Updated video {video.id} in database.")

    finally:
        db.close()

if __name__ == "__main__":
    main()
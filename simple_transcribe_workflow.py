from dotenv import load_dotenv
load_dotenv()

#!/usr/bin/env python3
"""
Simple workflow to transcribe your 5 videos and store in database
"""
import psycopg2
import requests
import tempfile
import os
import subprocess
import re

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host='localhost',
        database='interview_db',
        user='postgres',
        password=os.getenv('DB_PASSWORD'),
        port=5432
    )

def get_videos_to_process(limit=5):
    """Get videos that need transcription"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, video_url FROM interview_video 
           WHERE transcription IS NULL 
           OR transcription = %s
           LIMIT %s""",
        ('No clear speech detected', limit)
    )
    results = cur.fetchall()
    conn.close()
    return results

def download_video(url):
    """Download video from URL or copy local file"""
    if url.startswith('http://') or url.startswith('https://'):
        # It's a URL
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name
    else:
        # It's a local file
        if os.path.exists(url):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
                with open(url, 'rb') as src:
                    tmp.write(src.read())
                return tmp.name
        else:
            raise FileNotFoundError(f"File not found: {url}")

def extract_audio(video_path):
    """Extract audio from video"""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    audio_path = tempfile.mktemp(suffix=".wav")
    
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
    return audio_path

def transcribe_audio(audio_path):
    """Transcribe audio using Faster-Whisper"""
    from faster_whisper import WhisperModel
    print("  Loading Faster-Whisper model...")
    model = WhisperModel("tiny", device="auto", compute_type="int8")  # Faster processing
    
    print("  Transcribing...")
    segments, info = model.transcribe(audio_path, language='en')
    text = "".join([segment.text for segment in segments]).strip()
    text = re.sub(r'\s+', ' ', text)
    text = ''.join(c for c in text if c.isprintable() or c in '.,!?')
    return text.strip() if text and len(text) >= 2 else "No clear speech detected"

def update_database(video_id, transcription):
    """Update transcription in database"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE interview_video SET transcription = %s WHERE id = %s",
        (transcription, video_id)
    )
    conn.commit()
    conn.close()

def main():
    print("="*70)
    print("🎥 VIDEO TRANSCRIPTION WORKFLOW")
    print("="*70)
    
    videos = get_videos_to_process(5)
    
    if not videos:
        print("✅ All videos already have transcriptions!")
        return
    
    print(f"Found {len(videos)} videos to process\n")
    
    for i, (video_id, video_url) in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] Processing video {video_id}...")
        print(f"  URL: {video_url[:60]}...")
        
        video_path = None
        audio_path = None
        
        try:
            # Download
            print("  Downloading...")
            video_path = download_video(video_url)
            
            # Extract audio
            print("  Extracting audio...")
            audio_path = extract_audio(video_path)
            
            # Transcribe
            transcription = transcribe_audio(audio_path)
            print(f"  ✅ Transcription: {transcription[:50]}...")
            
            # Update database
            update_database(video_id, transcription)
            print(f"  ✅ Saved to database\n")
            
        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            print(f"  ❌ Error: {error_msg}\n")
            update_database(video_id, error_msg)
        
        finally:
            # Cleanup
            for path in [video_path, audio_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass
    
    print("="*70)
    print("✅ DONE! All transcriptions saved to database")
    print("="*70)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Standalone script to transcribe a video file to text
Usage: python transcribe_video.py <video_file_path>
"""
import sys
import os
import tempfile
import subprocess
import re

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
    model = WhisperModel("tiny", device="auto", compute_type="int8")  # Faster processing
    segments, info = model.transcribe(audio_path, language='en')
    transcription_text = "".join([segment.text for segment in segments]).strip()
    transcription_text = re.sub(r'\s+', ' ', transcription_text)
    transcription_text = ''.join(c for c in transcription_text if c.isprintable() or c in '.,!?')
    return transcription_text.strip()

def main(video_path):
    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        return

    print(f"Processing video: {video_path}")

    tmp_audio = None
    try:
        # Extract audio
        tmp_audio = tempfile.mktemp(suffix=".wav")
        extract_audio(video_path, tmp_audio)
        print("Audio extracted successfully")

        # Transcribe
        transcription = transcribe_audio(tmp_audio)
        if transcription and len(transcription) >= 2:
            print(f"Transcription: {transcription}")
        else:
            print("No clear speech detected")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if tmp_audio and os.path.exists(tmp_audio):
            os.remove(tmp_audio)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python transcribe_video.py <video_file_path>")
        sys.exit(1)

    main(sys.argv[1])
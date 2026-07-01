import os
from dotenv import load_dotenv
load_dotenv()

"""
Reprocess all existing videos with improved audio and face detection
"""

import psycopg2
from main import transcribe_video_only_task, initialize_database

# Ensure the database is initialized before processing
initialize_database()

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    database='interview_db',
    user='postgres',
    password=os.getenv('DB_PASSWORD'),
    port=5432
)
cur = conn.cursor()

try:
    # Get all videos
    cur.execute('SELECT id FROM interview_video ORDER BY id')
    videos = cur.fetchall()
    
    print(f"📊 Found {len(videos)} videos to reprocess")
    print(f"{'='*60}\n")
    
    for idx, (video_id,) in enumerate(videos, 1):
        print(f"[{idx}/{len(videos)}] Reprocessing video {video_id}...")
        try:
            transcribe_video_only_task(video_id)
        except Exception as e:
            print(f"  ❌ Error: {e}\n")
    
    print(f"\n{'='*60}")
    print(f"✨ Reprocessing complete!")
    
    # Show summary
    cur.execute('SELECT COUNT(*) FROM interview_video WHERE transcription IS NOT NULL')
    transcribed = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM interview_video WHERE expression_analysis IS NOT NULL')
    expressions = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM interview_video WHERE ai_feedback IS NOT NULL')
    feedback = cur.fetchone()[0]
    
    print(f"\n📈 SUMMARY:")
    print(f"  ✅ Videos with transcription: {transcribed}/{len(videos)}")
    print(f"  ✅ Videos with expression: {expressions}/{len(videos)}")
    print(f"  ✅ Videos with AI feedback: {feedback}/{len(videos)}")
    
finally:
    cur.close()
    conn.close()

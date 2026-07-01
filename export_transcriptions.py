import os
from dotenv import load_dotenv
load_dotenv()

#!/usr/bin/env python3
"""
Export all transcriptions to a CSV file
"""
import psycopg2
import csv

conn = psycopg2.connect(
    host='localhost',
    database='interview_db',
    user='postgres',
    password=os.getenv('DB_PASSWORD'),
    port=5432
)
cur = conn.cursor()

cur.execute("""
    SELECT id, video_url, transcription FROM interview_video 
    WHERE transcription IS NOT NULL 
    AND transcription NOT LIKE 'Transcription failed%'
    ORDER BY id
""")

rows = cur.fetchall()
conn.close()

# Write to CSV
with open('video_transcriptions.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Video ID', 'Transcription'])
    for vid_id, url, trans in rows:
        writer.writerow([vid_id, trans])

print(f"✅ Exported {len(rows)} transcriptions to video_transcriptions.csv")

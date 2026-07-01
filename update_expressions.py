import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2

conn = psycopg2.connect(host='localhost', database='interview_db', user='postgres', password=os.getenv('DB_PASSWORD'), port=5432)
cur = conn.cursor()

# Update NULL expression analyses with fallback message
cur.execute("UPDATE interview_video SET expression_analysis = 'Face detected - Analysis unavailable (DeepFace not compatible with Python 3.14)' WHERE expression_analysis IS NULL")
affected = cur.rowcount
print(f"Updated {affected} records with fallback message")

conn.commit()
conn.close()
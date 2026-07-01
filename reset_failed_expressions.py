import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2

conn = psycopg2.connect(host='localhost', database='interview_db', user='postgres', password=os.getenv('DB_PASSWORD'), port=5432)
cur = conn.cursor()

# Reset failed expression analyses so they get reprocessed
cur.execute("UPDATE interview_video SET expression_analysis = NULL WHERE expression_analysis = 'Analysis failed'")
affected = cur.rowcount
print(f"Reset {affected} videos with 'Analysis failed' for reprocessing")

conn.commit()
conn.close()
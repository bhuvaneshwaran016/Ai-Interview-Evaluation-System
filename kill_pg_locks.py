import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='interview_db',
    user='postgres',
    password=os.getenv('DB_PASSWORD'),
    port=5432
)
cur = conn.cursor()
cur.execute("SELECT pid FROM pg_stat_activity WHERE datname=%s AND state='idle in transaction' AND query LIKE 'SELECT interview_video%%'", ('interview_db',))
pids = [r[0] for r in cur.fetchall()]
print('TERMINATING', pids)
for pid in pids:
    cur.execute('SELECT pg_terminate_backend(%s)', (pid,))
conn.commit()
cur.close()
conn.close()

import os
from dotenv import load_dotenv
load_dotenv()

"""
Script to add missing columns to the interview_video table in PostgreSQL
Run this once to fix the database schema for session management
"""
import psycopg2
from psycopg2 import sql

# Database connection details
DB_HOST = "localhost"
DB_NAME = "interview_db"
DB_USER = "postgres"
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = 5432

try:
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

    cursor = conn.cursor()

    print("🔧 Checking and adding missing columns to interview_video table...\n")

    # Get existing columns
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'interview_video'
    """)
    existing_columns = {row[0] for row in cursor.fetchall()}
    print(f"✓ Existing columns: {existing_columns}\n")

    # Add session_id column if missing
    if 'session_id' not in existing_columns:
        try:
            cursor.execute("ALTER TABLE interview_video ADD COLUMN session_id VARCHAR NOT NULL DEFAULT 'legacy';")
            print("✅ Added session_id column")
        except Exception as e:
            print(f"❌ Error adding session_id: {e}")

    # Add transcription column if missing
    if 'transcription' not in existing_columns:
        try:
            cursor.execute("ALTER TABLE interview_video ADD COLUMN transcription VARCHAR;")
            print("✅ Added transcription column")
        except Exception as e:
            print(f"❌ Error adding transcription: {e}")

    # Add expression_analysis column if missing
    if 'expression_analysis' not in existing_columns:
        try:
            cursor.execute("ALTER TABLE interview_video ADD COLUMN expression_analysis VARCHAR;")
            print("✅ Added expression_analysis column")
        except Exception as e:
            print(f"❌ Error adding expression_analysis: {e}")

    # Add ai_feedback column if missing
    if 'ai_feedback' not in existing_columns:
        try:
            cursor.execute("ALTER TABLE interview_video ADD COLUMN ai_feedback VARCHAR;")
            print("✅ Added ai_feedback column")
        except Exception as e:
            print(f"❌ Error adding ai_feedback: {e}")

    # Commit changes
    conn.commit()

    print("\n✅ Database schema updated successfully!")

    # Verify the changes
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'interview_video'
        ORDER BY ordinal_position
    """)
    final_columns = [row[0] for row in cursor.fetchall()]
    print(f"📋 Final columns: {final_columns}")

except Exception as e:
    print(f"❌ Database error: {e}")
finally:
    if 'conn' in locals():
        cursor.close()
        conn.close()
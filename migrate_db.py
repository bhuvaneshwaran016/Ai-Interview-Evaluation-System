import os
from dotenv import load_dotenv
load_dotenv()

"""
Script to add missing columns to the candidates table in PostgreSQL
Run this once to fix the database schema
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
    
    print("🔧 Checking and adding missing columns to candidates table...\n")
    
    # List of columns to add with their definitions
    columns_to_add = [
        ("name", "VARCHAR(255)"),
        ("password", "VARCHAR(255)"),
        ("role", "VARCHAR(50)"),
        ("experience", "INTEGER"),
        ("phone", "VARCHAR(20)"),
    ]
    
    # Get existing columns
    cursor.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'candidates'
    """)
    existing_columns = {row[0] for row in cursor.fetchall()}
    print(f"✓ Existing columns: {existing_columns}\n")
    
    # Add missing columns
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            try:
                alter_query = f"ALTER TABLE candidates ADD COLUMN {col_name} {col_type};"
                cursor.execute(alter_query)
                print(f"✅ Added column: {col_name} ({col_type})")
            except Exception as e:
                print(f"⚠️  Could not add {col_name}: {str(e)}")
        else:
            print(f"✓ Column {col_name} already exists")
    
    conn.commit()
    print("\n✅ Database schema updated successfully!")
    
except Exception as e:
    print(f"❌ Error connecting to database: {str(e)}")
    print("\n📝 Make sure:")
    print("  1. PostgreSQL is running")
    print("  2. Database 'interview_db' exists")
    print("  3. User 'postgres' password is correct")
    
finally:
    if 'conn' in locals():
        conn.close()

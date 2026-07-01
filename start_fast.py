#!/usr/bin/env python3
"""
Lightweight startup script - minimal imports to avoid hangs
"""
import os
import sys

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

print("🚀 Starting Interview App (Fast Mode)")
print("=" * 70)

# Set timeout for imports
import signal

def timeout_handler(signum, frame):
    print("❌ Import took too long - there may be a module issue")
    sys.exit(1)

# Set 30-second timeout
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(30)

try:
    print("📦 Importing FastAPI...")
    import uvicorn
    print("✅ FastAPI imported")
    
    print("📦 Importing main app...")
    from main import app
    print("✅ Main app imported successfully")
    
    signal.alarm(0)  # Cancel alarm
    
    print("=" * 70)
    print("✅ Ready to start server")
    print("Server will run on: http://127.0.0.1:8000")
    print("=" * 70 + "\n")
    
    uvicorn.run(
        app,
        host='127.0.0.1',
        port=8000,
        log_level='info'
    )

except KeyboardInterrupt:
    print("\n✅ Server stopped by user")
    sys.exit(0)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

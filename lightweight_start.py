"""
Lightweight FastAPI launcher for Windows
Uses direct import to avoid module exhaustion issues
"""
import os
import sys

# Set up minimal environment
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

print("\n" + "="*70)
print("🚀 Loading Interview App (Windows-optimized)")
print("="*70)

try:
    print("📦 Importing main application...")
    from main import app
    print("✓ Application loaded successfully!")
    print("="*70 + "\n")
except Exception as e:
    print(f"❌ Failed to load app: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

if __name__ == '__main__':
    import uvicorn
    
    print("URL: http://127.0.0.1:8001")
    print("="*70 + "\n")
    
    try:
        uvicorn.run(
            app,
            host='127.0.0.1',
            port=8001,
            log_level='info'
        )
    except KeyboardInterrupt:
        print("\n\n✓ Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

"""Minimal wrapper to run FastAPI with Waitress - imports main lazily"""
import sys
import os

# Set environment before importing
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

def run_server():
    """Lazy import to avoid resource exhaustion"""
    try:
        print("Importing FastAPI app...")
        from main import app
        print("✓ App imported successfully")
        
        print("Starting Waitress server...")
        from waitress import serve
        
        print("=" * 70)
        print("FastAPI Server Running!")
        print("=" * 70)
        print("URL: http://127.0.0.1:8000")
        print("Press Ctrl+C to stop")
        print("=" * 70)
        
        serve(app, host='127.0.0.1', port=8000, threads=2)
        
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    run_server()

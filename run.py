import uvicorn
import os
import sys

# Ensure root directory in python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if __name__ == "__main__":
    print("=" * 70)
    print(" ClassSwap — Smart Substitutions. Zero Idle Hours.")
    print(" Academic Timetable & Faculty Substitution Management Platform")
    print("=" * 70)
    print(" Starting ClassSwap server on http://127.0.0.1:8000")
    print(" Default Login Accounts:")
    print("   HOD / Admin: admin@classswap.edu       | Password: Admin@123")
    print("   Faculty:     rajesh.kumar@classswap.edu | Password: Faculty@123")
    print("   Faculty:     priya.nair@classswap.edu   | Password: Faculty@123")
    print("=" * 70)

    use_reload = os.getenv("RELOAD", "true").lower() in ("true", "1", "yes")

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=use_reload
    )

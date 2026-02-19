"""
BCSD Child Nutrition Ops Console
Local compliance & memory system for school nutrition programs.

Run: python app.py
"""
if __name__ == "__main__":
    import subprocess
    import sys
    from pathlib import Path
    # Use python -m uvicorn so module resolution is correct when reloader spawns
    # Run from project root so main:app loads correctly
    project_root = Path(__file__).resolve().parent
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=str(project_root),
    )

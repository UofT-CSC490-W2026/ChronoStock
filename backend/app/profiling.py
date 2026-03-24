import cProfile
import os
import pstats
import re
import uvicorn

from app.main import app

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_PATH = APP_DIR
REPORT_PATH = os.path.join(APP_DIR, "report.txt")
NUM_REPORT = 10

def main() -> None:
    profiler = cProfile.Profile()
    profiler.runcall(uvicorn.run, app, host="127.0.0.1", port=8000)
    with open(REPORT_PATH, "w", encoding="utf-8") as report:
        stats = pstats.Stats(profiler, stream=report).sort_stats("cumulative")
        stats.print_stats(re.escape(BACKEND_PATH), NUM_REPORT)

    print(f"Report saved to {REPORT_PATH}")

if __name__ == "__main__":
    main()
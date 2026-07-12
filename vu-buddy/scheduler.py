import time
from datetime import datetime

from main import run_once


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SCHEDULER] {message}")


def start_scheduler() -> None:
    log("VU Buddy scheduler started. Interval: every 10 minutes.")
    while True:
        run_once()
        time.sleep(600)


if __name__ == "__main__":
    start_scheduler()

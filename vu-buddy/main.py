from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from config import DATABASE_PATH, LMS_URL, STATUS_PATH, effective_lms_id, effective_lms_password, effective_whatsapp_number
from detector import detect_new_items
from lms_login import login_to_lms
from check_assignments import fetch_assignments
from check_gdbs import fetch_gdbs
from check_quizzes import fetch_quizzes
from check_announcements import fetch_announcements
from whatsapp_notify import send_whatsapp_notification


logger = logging.getLogger("vu_buddy.main")


PROJECT_ROOT = Path(__file__).resolve().parent


CONTENT_TYPES = [
    ("assignments", fetch_assignments),
    ("gdbs", fetch_gdbs),
    ("quizzes", fetch_quizzes),
    ("announcements", fetch_announcements),
]


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.getenv("VU_BUDDY_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _write_status(*, status: str, total_new: int, notifications_sent: int, per_type_new: dict | None = None) -> None:
    existing_total = 0
    try:
        existing = json.loads((PROJECT_ROOT / STATUS_PATH).read_text(encoding="utf-8"))
        existing_total = int(existing.get("notifications_sent", 0) or 0)
    except Exception:
        existing_total = 0

    payload = {
        "status": status,
        "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "assignments_found": int(total_new),
        "notifications_sent": int(existing_total) + int(notifications_sent),
    }
    if per_type_new:
        payload["per_type"] = {k: int(v) for k, v in per_type_new.items()}
    (PROJECT_ROOT / STATUS_PATH).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_once() -> dict:
    """
    Runs one full cycle:
    - login (headless Selenium)
    - fetch assignments, GDBs, quizzes, announcements
    - detect new vs database.json
    - send WhatsApp alerts for new items
    - update status.json
    """
    driver = None
    notifications_sent = 0
    try:
        driver = login_to_lms(effective_lms_id(), effective_lms_password(), lms_url=LMS_URL)
        db_path = str((PROJECT_ROOT / DATABASE_PATH).resolve())

        all_new = {}
        totals = {}
        for ctype, fetcher in CONTENT_TYPES:
            items = fetcher(driver, lms_url=LMS_URL)
            totals[ctype] = len(items)
            new_items = detect_new_items(items, db_path, ctype)
            all_new[ctype] = new_items

        total_new = sum(len(v) for v in all_new.values())

        if total_new:
            for ctype, items in all_new.items():
                if items:
                    notification_type = ctype.rstrip("s")  # "assignments" -> "assignment"
                    notifications_sent += send_whatsapp_notification(effective_whatsapp_number(), items, content_type=notification_type)

        _write_status(
            status="running",
            total_new=total_new,
            notifications_sent=notifications_sent,
            per_type_new={k: len(v) for k, v in all_new.items()},
        )
        logger.info(
            "Cycle complete. a=%d g=%d q=%d an=%d new=%d whatsapp=%d",
            totals.get("assignments", 0),
            totals.get("gdbs", 0),
            totals.get("quizzes", 0),
            totals.get("announcements", 0),
            total_new,
            notifications_sent,
        )
        result = {f"{k}_total": v for k, v in totals.items()}
        result.update({f"new_{k}": len(v) for k, v in all_new.items()})
        result["notifications_sent"] = notifications_sent
        result["total_new"] = total_new
        return result
    except Exception:
        logger.exception("Cycle failed.")
        _write_status(status="error", total_new=0, notifications_sent=notifications_sent)
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def run_scheduler_loop(*, interval_seconds: int = 600) -> None:
    logger.info("Scheduler started. Interval: %ds", interval_seconds)
    while True:
        run_once()
        time.sleep(interval_seconds)


def run_dashboard() -> None:
    from frontend.app import app  # local import to keep bot-only runs lightweight

    host = os.getenv("VU_BUDDY_HOST", "0.0.0.0")
    port = int(os.getenv("VU_BUDDY_PORT", "5000"))
    debug = os.getenv("VU_BUDDY_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug)


def main(argv: list[str]) -> None:
    _setup_logging()

    # `python main.py dashboard` keeps the existing Flask UI behavior.
    if len(argv) >= 2 and argv[1].lower() == "dashboard":
        run_dashboard()
        return

    # Default: run the headless LMS checker scheduler loop.
    run_scheduler_loop(interval_seconds=600)


if __name__ == "__main__":
    main(sys.argv)

import os
from datetime import datetime
from pathlib import Path
import sys
import json
import pywhatkit
import threading
from flask import Flask, jsonify, render_template, request


# Allow importing existing backend modules from parent project folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import (  # noqa: E402
    LMS_URL,
    effective_lms_id,
    effective_lms_password,
    EMAIL_SENDER,
    EMAIL_PASSWORD,
    EMAIL_RECEIVER,
    EMAIL_FROM,
    effective_whatsapp_number,
    DATABASE_PATH,
    STATUS_PATH,
)
from lms_login import login_to_lms  # noqa: E402
from check_assignments import fetch_assignments  # noqa: E402
from check_gdbs import fetch_gdbs  # noqa: E402
from check_quizzes import fetch_quizzes  # noqa: E402
from check_announcements import fetch_announcements  # noqa: E402
from detector import detect_new_items  # noqa: E402
from email_notify import send_email_notification  # noqa: E402
from whatsapp_notify import send_whatsapp_notification  # noqa: E402

app = Flask(__name__)


CONTENT_FETCHERS = [
    ("assignments", fetch_assignments),
    ("gdbs", fetch_gdbs),
    ("quizzes", fetch_quizzes),
    ("announcements", fetch_announcements),
]

NOTIFICATION_TYPES = ["assignment", "gdb", "quiz", "announcement"]

bot_state = {
    "is_running": False,
    "last_check_time": "Never",
    "assignments_new": 0,
    "gdbs_new": 0,
    "quizzes_new": 0,
    "announcements_new": 0,
    "assignments_total": 0,
    "gdbs_total": 0,
    "quizzes_total": 0,
    "announcements_total": 0,
    "total_new": 0,
    "notifications_sent": 0,
    "last_notification": "None",
    "last_error": "",
}

# Cache of items from the last successful check (for test buttons)
_last_fetched_items: dict[str, list[dict]] = {
    "assignment": [],
    "gdb": [],
    "quiz": [],
    "announcement": [],
}

settings_state = {
    "whatsapp_enabled": True,
    "email_enabled": True,
    "check_interval": 5,
}

logs = [
    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Dashboard initialized.",
]
state_lock = threading.Lock()
stop_event = threading.Event()
bot_thread = None


def add_log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logs.insert(0, f"[{timestamp}] {message}")
    del logs[50:]


def _validate_runtime_config() -> None:
    missing = []
    if not LMS_URL:
        missing.append("LMS_URL")
    if not effective_lms_id():
        missing.append("LMS_ID")
    if not effective_lms_password():
        missing.append("LMS_PASSWORD")

    if settings_state["email_enabled"]:
        if not EMAIL_SENDER:
            missing.append("EMAIL_SENDER")
        if not EMAIL_PASSWORD:
            missing.append("EMAIL_PASSWORD")
        if not EMAIL_RECEIVER:
            missing.append("EMAIL_RECEIVER")

    if settings_state["whatsapp_enabled"]:
        if not effective_whatsapp_number():
            missing.append("WHATSAPP_NUMBER")

    if missing:
        raise ValueError("Missing required environment variables: " + ", ".join(missing))


def _execute_check(trigger_source: str) -> None:
    driver = None
    try:
        _validate_runtime_config()
        db_path = str((PROJECT_ROOT / DATABASE_PATH).resolve())
        add_log(f"Bot check started ({trigger_source}).")

        driver = login_to_lms(effective_lms_id(), effective_lms_password(), lms_url=LMS_URL)

        # Fetch all 4 content types and cache them
        all_new = {}
        totals = {}
        global _last_fetched_items
        for ctype, fetcher in CONTENT_FETCHERS:
            try:
                items = fetcher(driver, lms_url=LMS_URL)
                totals[ctype] = len(items)
                new_items = detect_new_items(items, db_path, ctype)
                all_new[ctype] = new_items
                # Cache for test buttons
                ctype_key = ctype.rstrip("s")  # "assignments" -> "assignment"
                _last_fetched_items[ctype_key] = items
                add_log(f"Fetched {len(items)} {ctype}, {len(new_items)} new.")
            except Exception as exc:
                add_log(f"Failed to fetch {ctype}: {exc}")
                totals[ctype] = 0
                all_new[ctype] = []

        total_new = sum(len(v) for v in all_new.values())

        with state_lock:
            bot_state["last_check_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for ctype in ["assignments", "gdbs", "quizzes", "announcements"]:
                bot_state[f"{ctype}_new"] = len(all_new.get(ctype, []))
                bot_state[f"{ctype}_total"] = totals.get(ctype, 0)
            bot_state["total_new"] = total_new

        _write_status_file(
            status_path=str((PROJECT_ROOT / STATUS_PATH).resolve()),
            status="running",
            total_new=total_new,
            notifications_sent=bot_state["notifications_sent"],
        )

        if not total_new:
            add_log("No new items found.")
            return

        add_log(f"New items found: {total_new}")
        notification_count = 0

        if settings_state["email_enabled"] or settings_state["whatsapp_enabled"]:
            for ctype, items in all_new.items():
                if not items:
                    continue
                ntype = ctype.rstrip("s")  # "assignments" -> "assignment"
                if settings_state["email_enabled"]:
                    send_email_notification(
                        sender_email=EMAIL_SENDER,
                        sender_password=EMAIL_PASSWORD,
                        receiver_email=EMAIL_RECEIVER,
                        items=items,
                        content_type=ntype,
                    )
                    notification_count += 1
                    with state_lock:
                        bot_state["last_notification"] = f"Email sent at {datetime.now().strftime('%H:%M:%S')}"
                    add_log(f"Email notification sent for {ntype}.")
                if settings_state["whatsapp_enabled"]:
                    sent = send_whatsapp_notification(
                        phone=effective_whatsapp_number(),
                        items=items,
                        content_type=ntype,
                    )
                    notification_count += sent
                    with state_lock:
                        bot_state["last_notification"] = f"WhatsApp sent at {datetime.now().strftime('%H:%M:%S')}"
                    add_log(f"WhatsApp notification sent for {ntype}.")

        with state_lock:
            bot_state["notifications_sent"] += notification_count
            bot_state["last_error"] = ""

        _write_status_file(
            status_path=str((PROJECT_ROOT / STATUS_PATH).resolve()),
            status="running",
            total_new=total_new,
            notifications_sent=bot_state["notifications_sent"],
        )

    except Exception as exc:
        with state_lock:
            bot_state["last_error"] = str(exc)
        add_log(f"Run failed: {exc}")
        try:
            _write_status_file(
                status_path=str((PROJECT_ROOT / STATUS_PATH).resolve()),
                status="error",
                total_new=0,
                notifications_sent=bot_state["notifications_sent"],
                last_error=str(exc),
            )
        except Exception:
            pass
    finally:
        if driver is not None:
            driver.quit()
            add_log("Browser session closed.")


def _write_status_file(
    *,
    status_path: str,
    status: str,
    total_new: int,
    notifications_sent: int,
    last_error: str = "",
) -> None:
    payload = {
        "status": status,
        "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "assignments_found": int(total_new),
        "notifications_sent": int(notifications_sent),
    }
    if last_error:
        payload["last_error"] = last_error
    Path(status_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _bot_loop() -> None:
    while not stop_event.is_set():
        _execute_check("auto")
        wait_seconds = max(1, int(settings_state["check_interval"])) * 60
        if stop_event.wait(wait_seconds):
            break

    with state_lock:
        bot_state["is_running"] = False
    add_log("Background bot loop stopped.")


def _start_bot_loop() -> bool:
    global bot_thread
    with state_lock:
        already_running = bot_state["is_running"]
    if already_running and bot_thread and bot_thread.is_alive():
        return False

    stop_event.clear()
    with state_lock:
        bot_state["is_running"] = True

    bot_thread = threading.Thread(target=_bot_loop, daemon=True)
    bot_thread.start()
    add_log("Background bot loop started.")
    return True


@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/settings")
def settings():
    return render_template("settings.html")


@app.route("/logs")
def logs_page():
    return render_template("logs.html")


@app.route("/api/status")
def get_status():
    with state_lock:
        status = dict(bot_state)
    return jsonify(status)


@app.route("/api/settings", methods=["GET", "POST"])
def settings_api():
    if request.method == "GET":
        return jsonify(settings_state)

    payload = request.get_json(silent=True) or {}
    settings_state["whatsapp_enabled"] = bool(payload.get("whatsapp_enabled", settings_state["whatsapp_enabled"]))
    settings_state["email_enabled"] = bool(payload.get("email_enabled", settings_state["email_enabled"]))
    settings_state["check_interval"] = max(1, int(payload.get("check_interval", settings_state["check_interval"])))
    add_log(
        "Settings saved: "
        f"WhatsApp={'ON' if settings_state['whatsapp_enabled'] else 'OFF'}, "
        f"Email={'ON' if settings_state['email_enabled'] else 'OFF'}, "
        f"Interval={settings_state['check_interval']} min."
    )
    return jsonify({"ok": True, "settings": settings_state})


@app.route("/run", methods=["POST"])
def run_bot():
    _execute_check("manual")
    return jsonify({"ok": True, "message": "Manual check completed."})


@app.route("/start", methods=["POST"])
def start_bot():
    started = _start_bot_loop()
    if started:
        return jsonify({"ok": True, "message": "Bot started in background mode."})
    return jsonify({"ok": True, "message": "Bot is already running."})


@app.route("/stop", methods=["POST"])
def stop_bot():
    stop_event.set()
    with state_lock:
        bot_state["is_running"] = False
    add_log("Bot stopped from dashboard.")
    return jsonify({"ok": True, "message": "Bot stopped."})


@app.route("/test", methods=["POST"])
def test_notification():
    payload = request.get_json(silent=True) or {}
    channel = payload.get("channel", "notification")
    content_type = payload.get("content_type", "assignment")

    # Use cached items from the last run
    cached = _last_fetched_items.get(content_type, [])
    if cached:
        items = cached
    else:
        # If nothing cached, run a fresh fetch using the existing driver from _execute_check
        add_log(f"No cached {content_type}s. Triggering a check first...")
        _execute_check("test_button")
        cached = _last_fetched_items.get(content_type, [])
        if cached:
            items = cached
        else:
            return jsonify({"ok": False, "message": f"No {content_type}s found yet. Click Run Now first."}), 400

    try:
        if channel == "email":
            if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECEIVER:
                raise ValueError("Email environment variables are missing.")
            send_email_notification(
                sender_email=EMAIL_SENDER,
                sender_password=EMAIL_PASSWORD,
                receiver_email=EMAIL_RECEIVER,
                items=items,
                content_type=content_type,
            )
        elif channel == "whatsapp":
            if not effective_whatsapp_number():
                raise ValueError("WhatsApp environment variables are missing.")
            send_whatsapp_notification(phone=effective_whatsapp_number(), items=items, content_type=content_type)
        else:
            raise ValueError("Unsupported notification channel.")

        with state_lock:
            bot_state["notifications_sent"] += 1
            bot_state["last_notification"] = f"{content_type.title()} {channel.title()} test at {datetime.now().strftime('%H:%M:%S')}"
            bot_state["last_error"] = ""
        add_log(f"Sent test {channel} {content_type} notification.")
        return jsonify({"ok": True, "message": f"Test {content_type} {channel} notification sent."})
    except Exception as exc:
        with state_lock:
            bot_state["last_error"] = str(exc)
        add_log(f"Test {channel} {content_type} notification failed: {exc}")
        return jsonify({"ok": False, "message": str(exc)}), 400


@app.route("/api/logs")
def get_logs():
    with state_lock:
        status = dict(bot_state)
    return jsonify(
        {
            "logs": logs[:30],
            "last_notification": status["last_notification"],
            "notifications_sent": status["notifications_sent"],
        }
    )

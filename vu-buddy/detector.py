import json
from datetime import datetime
from pathlib import Path


DEFAULT_DB = {
    "assignments": [],
    "gdbs": [],
    "quizzes": [],
    "announcements": [],
}

TYPE_LABELS = {
    "assignments": "Assignment",
    "gdbs": "GDB",
    "quizzes": "Quiz",
    "announcements": "Announcement",
}


def _log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [DETECTOR] {message}")


def _read_database(db_path: str) -> dict:
    path = Path(db_path)
    if not path.exists():
        _log("Database not found. Creating a new one...")
        data = dict(DEFAULT_DB)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Migrate old format (only "assignments" key) to 4-key format
        migrated = False
        for key in DEFAULT_DB:
            if key not in data:
                data[key] = list(DEFAULT_DB[key])
                migrated = True
        if migrated:
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            _log("Migrated database to multi-type format.")
        return data
    except json.JSONDecodeError:
        _log("Corrupted database.json detected. Resetting file...")
        data = dict(DEFAULT_DB)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data


def _write_database(db_path: str, content_type: str, items: list[dict]) -> None:
    path = Path(db_path)
    data = _read_database(db_path)
    data[content_type] = items
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def detect_new_items(current_items: list[dict], db_path: str, content_type: str) -> list[dict]:
    """
    Generic detector for any content type.
    content_type: one of "assignments", "gdbs", "quizzes", "announcements"
    Returns items with IDs not previously seen for that type.
    """
    db_data = _read_database(db_path)
    old_ids = {item.get("id") for item in db_data.get(content_type, [])}
    new_items = [item for item in current_items if item.get("id") not in old_ids]
    _write_database(db_path, content_type, current_items)
    label = TYPE_LABELS.get(content_type, content_type.title())
    _log(f"Detected {len(new_items)} new {label}(s).")
    return new_items


# Backward-compatible wrapper
def detect_new_assignments(current_assignments: list[dict], db_path: str) -> list[dict]:
    return detect_new_items(current_assignments, db_path, "assignments")

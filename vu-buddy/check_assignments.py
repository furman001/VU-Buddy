from __future__ import annotations

import hashlib
import logging

from lms_nav import _normalize, scrape_all_courses

logger = logging.getLogger("vu_buddy.check_assignments")


def _make_assignment_id(subject: str, title: str, due_date: str) -> str:
    raw = f"{subject}|{title}|{due_date}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_assignments(driver, *, lms_url: str = "https://vulms.vu.edu.pk") -> list[dict]:
    all_course_items = scrape_all_courses(driver, lms_url, "assignments")

    assignments: list[dict] = []

    for course_idx, items in enumerate(all_course_items):
        for item in items:
            subject = item.get("_course_subject", "Course")
            title = item.get("title", "")
            due_date = item.get("due_date", "")
            status = item.get("status", item.get("score", ""))

            if not title or title.lower() in {"-", "n/a", ""}:
                continue

            assignments.append({
                "id": _make_assignment_id(subject, title, due_date),
                "subject": subject,
                "title": title,
                "due_date": due_date,
                "status": status,
            })

    unique: dict[str, dict] = {}
    for item in assignments:
        unique[item["id"]] = item
    result = list(unique.values())

    logger.info("Fetched %d assignment(s) across %d course(s).", len(result), len(all_course_items))
    return result

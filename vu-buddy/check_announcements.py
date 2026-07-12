from __future__ import annotations

import hashlib
import logging

from lms_nav import scrape_all_courses

logger = logging.getLogger("vu_buddy.check_announcements")


def _make_announcement_id(subject: str, title: str, date: str) -> str:
    raw = f"announcement|{subject}|{title}|{date}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_announcements(driver, *, lms_url: str = "https://vulms.vu.edu.pk") -> list[dict]:
    all_course_items = scrape_all_courses(driver, lms_url, "announcements")

    announcements: list[dict] = []

    for items in all_course_items:
        for item in items:
            subject = item.get("_course_subject", "Unknown")
            title = item.get("title", "")
            date = item.get("date", item.get("due_date", ""))
            details = item.get("details", "")

            if not title:
                continue

            announcements.append({
                "id": _make_announcement_id(subject, title, date),
                "subject": subject,
                "title": title,
                "date": date,
                "details": details,
            })

    unique: dict[str, dict] = {}
    for item in announcements:
        unique[item["id"]] = item
    result = list(unique.values())

    logger.info("Fetched %d announcement(s) across %d course(s).", len(result), len(all_course_items))
    return result

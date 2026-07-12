from __future__ import annotations

import hashlib
import logging

from lms_nav import scrape_all_courses

logger = logging.getLogger("vu_buddy.check_gdbs")


def _make_gdb_id(subject: str, title: str, start_date: str, end_date: str) -> str:
    raw = f"gdb|{subject}|{title}|{start_date}|{end_date}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_gdbs(driver, *, lms_url: str = "https://vulms.vu.edu.pk") -> list[dict]:
    all_course_items = scrape_all_courses(driver, lms_url, "gdbs")

    gdbs: list[dict] = []

    for items in all_course_items:
        for item in items:
            subject = item.get("_course_subject", "Unknown")
            title = item.get("title", "")
            start_date = item.get("start_date", "")
            end_date = item.get("due_date", item.get("end_date", ""))
            total_marks = item.get("total_marks", "")
            status = item.get("status", "")
            score = item.get("score", "")

            if not title:
                continue

            gdbs.append({
                "id": _make_gdb_id(subject, title, start_date, end_date),
                "subject": subject,
                "title": title,
                "opening_date": start_date,
                "closing_date": end_date,
                "total_marks": total_marks,
                "status": status,
                "score": score,
            })

    unique: dict[str, dict] = {}
    for item in gdbs:
        unique[item["id"]] = item
    result = list(unique.values())

    logger.info("Fetched %d GDB(s) across %d course(s).", len(result), len(all_course_items))
    return result

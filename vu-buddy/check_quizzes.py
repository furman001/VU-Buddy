from __future__ import annotations

import hashlib
import logging

from lms_nav import scrape_all_courses

logger = logging.getLogger("vu_buddy.check_quizzes")


def _make_quiz_id(subject: str, title: str, end_date: str) -> str:
    raw = f"quiz|{subject}|{title}|{end_date}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_quizzes(driver, *, lms_url: str = "https://vulms.vu.edu.pk") -> list[dict]:
    all_course_items = scrape_all_courses(driver, lms_url, "quizzes")

    quizzes: list[dict] = []

    for items in all_course_items:
        for item in items:
            subject = item.get("_course_subject", "Unknown")
            title = item.get("title", "")
            end_date = item.get("end_date", item.get("due_date", ""))
            start_date = item.get("start_date", "")
            total_marks = item.get("total_marks", "")
            status = item.get("status", "")

            if not title:
                continue

            quizzes.append({
                "id": _make_quiz_id(subject, title, end_date),
                "subject": subject,
                "title": title,
                "due_date": end_date,
                "start_date": start_date,
                "total_marks": total_marks,
                "status": status,
            })

    unique: dict[str, dict] = {}
    for item in quizzes:
        unique[item["id"]] = item
    result = list(unique.values())

    logger.info("Fetched %d quiz(zes) across %d course(s).", len(result), len(all_course_items))
    return result

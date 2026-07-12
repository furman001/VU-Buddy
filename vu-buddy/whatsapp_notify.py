from __future__ import annotations

import logging
from typing import Iterable

import pywhatkit


logger = logging.getLogger("vu_buddy.whatsapp")

TYPE_LABELS = {
    "assignment": "Assignment",
    "gdb": "GDB",
    "quiz": "Quiz",
    "announcement": "Announcement",
}


def _format_message(item: dict, content_type: str = "assignment") -> str:
    label = TYPE_LABELS.get(content_type, content_type.title())
    lines = [
        "VU Buddy Alert",
        f"New {label} Found",
        "",
        f"Subject: {item.get('subject', '')}",
        f"Title: {item.get('title', '')}",
    ]
    if item.get("due_date"):
        lines.append(f"Due Date: {item['due_date']}")
    if item.get("opening_date"):
        lines.append(f"Opening Date: {item['opening_date']}")
    if item.get("closing_date"):
        lines.append(f"Closing Date: {item['closing_date']}")
    if item.get("date"):
        lines.append(f"Date: {item['date']}")
    if item.get("total_marks"):
        lines.append(f"Marks: {item['total_marks']}")
    return "\n".join(lines).strip()


def send_whatsapp_notification(phone: str, items: Iterable[dict], content_type: str = "assignment") -> int:
    """
    Send WhatsApp message via pywhatkit.

    Note: pywhatkit uses WhatsApp Web and requires that the machine running this code
    has access to a browser session where WhatsApp Web can be used (first time needs QR scan).
    """
    sent = 0
    for item in list(items):
        message = _format_message(item, content_type=content_type)
        try:
            logger.info("Sending WhatsApp alert for: %s (%s)", item.get("title", "N/A"), content_type)
            pywhatkit.sendwhatmsg_instantly(phone, message, wait_time=20, tab_close=True, close_time=3)
            sent += 1
            logger.info("WhatsApp alert sent.")
        except Exception:
            logger.exception("Failed to send WhatsApp alert.")
            raise

    return sent

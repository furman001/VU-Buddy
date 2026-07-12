import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from config import SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS, EMAIL_FROM

TYPE_LABELS = {
    "assignment": "Assignment",
    "gdb": "GDB",
    "quiz": "Quiz",
    "announcement": "Announcement",
}


def _log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] {message}")


def send_email_notification(
    sender_email: str,
    sender_password: str,
    receiver_email: str,
    items: list[dict],
    content_type: str = "assignment",
) -> None:
    if not items:
        return

    label = TYPE_LABELS.get(content_type, content_type.title())

    lines = []
    for item in items:
        lines.append(f"New {label} Detected")
        lines.append(f"Subject: {item.get('subject', '')}")
        lines.append(f"Title: {item.get('title', '')}")
        if item.get("due_date"):
            lines.append(f"Due Date: {item['due_date']}")
        if item.get("opening_date"):
            lines.append(f"Opening Date: {item['opening_date']}")
        if item.get("closing_date"):
            lines.append(f"Closing Date: {item['closing_date']}")
        if item.get("date"):
            lines.append(f"Date: {item['date']}")
        if item.get("total_marks"):
            lines.append(f"Total Marks: {item['total_marks']}")
        if item.get("details"):
            lines.append(f"Details: {item['details']}")
        lines.append("")

    body = "\n".join(lines).strip()
    message = MIMEText(body)
    message["Subject"] = f"VU Buddy Alert - New {label}"
    message["From"] = EMAIL_FROM or sender_email
    message["To"] = receiver_email

    try:
        _log(f"Sending email via {SMTP_SERVER}:{SMTP_PORT} to {receiver_email}...")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [receiver_email], message.as_string())
        _log("Email sent successfully.")
    except Exception as exc:
        _log(f"Failed to send email: {exc}")
        raise

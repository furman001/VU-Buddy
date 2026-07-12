import os
from dotenv import load_dotenv


load_dotenv()


LMS_URL = os.getenv("LMS_URL", "https://vulms.vu.edu.pk")
# New env var names (preferred).
LMS_ID = os.getenv("LMS_ID", "").strip()
LMS_PASSWORD = os.getenv("LMS_PASSWORD", "")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "").strip()

# Backward compatible names (older project env keys).
LMS_USER = os.getenv("LMS_USER", "").strip()
LMS_PASS = os.getenv("LMS_PASS", "")
WHATSAPP_PHONE = os.getenv("WHATSAPP_PHONE", "").strip()

EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "") or EMAIL_SENDER
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.office365.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}

WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "")

DATABASE_PATH = os.getenv("DATABASE_PATH", "database.json")
STATUS_PATH = os.getenv("STATUS_PATH", "status.json")


def effective_lms_id() -> str:
    return LMS_ID or LMS_USER


def effective_lms_password() -> str:
    return LMS_PASSWORD or LMS_PASS


def effective_whatsapp_number() -> str:
    return WHATSAPP_NUMBER or WHATSAPP_PHONE


def validate_required_env() -> None:
    required = {
        "LMS_URL": LMS_URL,
        "EMAIL_SENDER": EMAIL_SENDER,
        "EMAIL_PASSWORD": EMAIL_PASSWORD,
        "EMAIL_RECEIVER": EMAIL_RECEIVER,
    }

    # New required keys for this feature set. We validate effective values so old keys still work.
    if not effective_lms_id():
        required["LMS_ID (or LMS_USER)"] = ""
    if not effective_lms_password():
        required["LMS_PASSWORD (or LMS_PASS)"] = ""

    # For pywhatkit notifications.
    if not effective_whatsapp_number():
        required["WHATSAPP_NUMBER (or WHATSAPP_PHONE)"] = ""

    missing = [name for name, value in required.items() if not value]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Missing required environment variables: {names}")

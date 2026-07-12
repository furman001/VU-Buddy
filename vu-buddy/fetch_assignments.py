import hashlib
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


def _log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [FETCH] {message}")


def _normalize(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _make_assignment_id(subject: str, title: str, due_date: str) -> str:
    raw = f"{subject}|{title}|{due_date}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_assignments(driver, lms_url: str) -> list[dict]:
    """
    Navigate to assignments page and scrape assignment records.
    """
    assignment_urls = [
        f"{lms_url.rstrip('/')}/Assignments.aspx",
        f"{lms_url.rstrip('/')}/pages/StudentAssignments.aspx",
    ]

    loaded = False
    for url in assignment_urls:
        try:
            _log(f"Opening assignments page: {url}")
            driver.get(url)
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            loaded = True
            break
        except TimeoutException:
            _log(f"Timeout loading: {url}")

    if not loaded:
        raise RuntimeError("Unable to load assignment page.")

    soup = BeautifulSoup(driver.page_source, "html.parser")
    assignments: list[dict] = []

    # Try to parse table rows first (common VULMS layout).
    for row in soup.select("table tr"):
        cols = [_normalize(col.get_text(" ", strip=True)) for col in row.find_all(["td", "th"])]
        if len(cols) < 3:
            continue

        header_like = " ".join(cols).lower()
        if "title" in header_like and "subject" in header_like:
            continue

        subject = cols[0]
        title = cols[1]
        due_date = cols[2]
        status = cols[3] if len(cols) >= 4 else ""

        if not title or title.lower() in {"-", "n/a"}:
            continue

        item = {
            "id": _make_assignment_id(subject, title, due_date),
            "subject": subject,
            "title": title,
            "due_date": due_date,
            "status": status,
        }
        assignments.append(item)

    # Fallback parser for card/list views.
    if not assignments:
        _log("Table parser found no items. Trying generic fallback parser...")
        for block in soup.select("div, li"):
            text = _normalize(block.get_text(" ", strip=True))
            if not text or "assignment" not in text.lower():
                continue
            parts = text.split("|")
            if len(parts) < 3:
                continue
            subject, title, due_date = parts[0], parts[1], parts[2]
            assignments.append(
                {
                    "id": _make_assignment_id(subject, title, due_date),
                    "subject": subject,
                    "title": title,
                    "due_date": due_date,
                }
            )

    # Deduplicate by id.
    unique: dict[str, dict] = {}
    for item in assignments:
        unique[item["id"]] = item

    result = list(unique.values())
    _log(f"Fetched {len(result)} assignment(s).")
    return result

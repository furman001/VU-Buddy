

from __future__ import annotations

import logging
import re
import time

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("vu_buddy.lms_nav")


# ── helpers ──────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _extract_course_code(page_text: str) -> str:
    m = re.search(r"\b([A-Z]{2,4}\d{3,4})\b", page_text)
    return m.group(1).upper() if m else "Unknown"


# ── click helpers ────────────────────────────────────────────────────────

BUTTON_ID_TEMPLATES: dict[str, str] = {
    "assignments": "MainContent_gvCourseList_ibtnAssignments_{idx}",
    "quizzes": "MainContent_gvCourseList_ibtnQuizzes_{idx}",
    "gdbs": "MainContent_gvCourseList_ibtnGDB_{idx}",
    "announcements": "MainContent_gvCourseList_ibtnnnouncements_11_{idx}",
}

TILE_REPEATER_IDS: dict[str, str] = {
    "assignments": "MainContent_gvTileRepeaterAssignment",
    "quizzes": "MainContent_gvTileRepeaterQuiz",
    "gdbs": "MainContent_gvTileRepeaterGDB",
}

# ── per-type tile span maps ──────────────────────────────────────────────
# Maps (field_name -> span_suffix) for each tile type
# The full span IDs follow the pattern: {repeater_id}_{suffix}_{panel_index}

TILE_MAPS: dict[str, dict[str, str]] = {
    "assignments": {
        "title": "lblTitle",
        "due_date": "lblDueDate",
        "total_marks": "lblTotalMarks",
        "status": "lblStatus",
        "score": "lblScore",
        "lesson": "lblPayableAmount",
    },
    "quizzes": {
        "title": "lblTitle",
        "start_date": "lblStartDate",
        "due_date": "lblEndDate",
        "total_marks": "lblTotalMarks",
        "status": "lblStatus",
        "score": "lblGetMarks",
    },
    # NOTE: GDB Label IDs (Label9, Label4, Label3) are ASP.NET auto-generated
    # and change per semester. The text-based _parse_tile_by_text() runs
    # first and handles GDBs correctly without relying on these IDs.
    "gdbs": {
        "title": "lblTitle",
        "total_marks": "Label9",
        "start_date": "Label4",
        "due_date": "Label3",
        "status": "lblStatus",
        "score": "lblMarksObtained",
        "submission_status": "lblSubmissionStatus",
    },
}


def _get_course_count(driver) -> int:
    buttons = driver.find_elements(
        By.CSS_SELECTOR, "input[type='image'][id*='ibtnAssignments']"
    )
    return len(buttons)


def _click_button(driver, btn_id: str) -> bool:
    try:
        btn = driver.find_element(By.ID, btn_id)
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(5)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return True
    except Exception as exc:
        logger.warning("Could not click %s: %s", btn_id, exc)
        return False


# ── unified tile parser ─────────────────────────────────────────────────

def _parse_tile_panels(
    soup: BeautifulSoup,
    repeater_id: str,
    tile_map: dict[str, str],
    course_code: str,
) -> list[dict]:
    """
    Parse tile panels by matching known span IDs.
    Each panel is <div id="{repeater_id}_pnl_N"> containing <span> elements
    with IDs like {repeater_id}_{suffix}_{N}.
    """
    items: list[dict] = []
    pnl_pat = re.compile(re.escape(repeater_id) + r"_pnl_(\d+)")
    pnl_divs = soup.find_all("div", id=pnl_pat)

    for pnl in pnl_divs:
        item: dict[str, str] = {}
        item["_course_subject"] = course_code
        item["_course_index"] = None

        for field_key, suffix in tile_map.items():
            span = pnl.find(
                "span",
                id=re.compile(
                    re.escape(repeater_id) + re.escape(f"_{suffix}_") + r"\d+"
                ),
            )
            if span:
                text = _normalize(span.get_text())
                if text and text not in ("-", "N/A", ":"):
                    item[field_key] = text

        # Extract panel index
        m = pnl_pat.match(pnl.get("id", ""))
        if m:
            item["_course_index"] = int(m.group(1))

        # Title fallback: look for the tile header text
        if "title" not in item:
            header = pnl.select_one(
                "[class*='tileHeader'], [class*='header'], span[style*='color']"
            )
            if header:
                t = _normalize(header.get_text())
                t = re.sub(r"^\d+\s*-\s*", "", t)
                if t:
                    item["title"] = t

        items.append(item)

    return items


# ── generic tile parser (by text, not span IDs) ──────────────────────────

def _parse_tile_by_text(
    soup: BeautifulSoup,
    repeater_id: str,
    course_code: str,
) -> list[dict]:
    """
    Parse tile panels by scanning their *text content* rather than relying
    on specific span-ID suffixes.  This handles quiz / GDB pages where the
    ASP.NET auto-generated Label IDs are unpredictable.

    For each panel div it extracts:
      - title       → the first substantial text line
      - start_date  → earliest date found
      - due_date    → latest date found
      - total_marks → number next to "Marks" / "Total"
      - score       → number next to "Obtained" / "Marks Obtained"
      - status      → keyword like Submitted, Expired, Overdue, Result Declared
    """
    items: list[dict] = []
    pnl_pat = re.compile(re.escape(repeater_id) + r"_pnl_(\d+)")
    pnl_divs = soup.find_all("div", id=pnl_pat)

    DATE_RE = re.compile(r"([A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})")
    MARKS_RE = re.compile(r"(\d+(?:\.\d+)?)")
    STATUS_KEYWORDS = [
        "not submitted", "result declared", "submitted", "expired",
        "overdue", "attempted", "missed",
    ]

    for pnl in pnl_divs:
        item: dict[str, str] = {
            "_course_subject": course_code,
            "_course_index": None,
        }

        # Collect all visible text tokens from panel
        all_spans = pnl.find_all(["span", "label", "td"])
        texts = [_normalize(el.get_text()) for el in all_spans]
        texts = [t for t in texts if t and t not in ("-", "N/A", ":")]

        # Extract dates
        dates: list[str] = []
        for t in texts:
            dates.extend(DATE_RE.findall(t))
        if dates:
            # Sort chronologically — earliest = start, latest = due
            dates.sort(key=lambda d: time.strptime(d.replace(",", "").strip(), "%b %d %Y"))
            item["start_date"] = dates[0]
            if len(dates) > 1:
                item["due_date"] = dates[-1]
            else:
                item["due_date"] = dates[0]

        # Extract status keyword (strip prefix like "Status: ")
        lower_texts = [t.lower() for t in texts]
        for kw in STATUS_KEYWORDS:
            for raw_t, lower_t in zip(texts, lower_texts):
                if kw in lower_t:
                    # Extract just the keyword portion from the matched text
                    idx = lower_t.find(kw)
                    extracted = raw_t[idx:idx + len(kw)]
                    item["status"] = extracted.title() if extracted.islower() else extracted
                    break
            if "status" in item:
                break

        # Determine title — first substantial non-date/non-marks text
        title = None
        for t in texts:
            if not DATE_RE.search(t) and not any(kw in t.lower() for kw in
                ("marks", "total", "obtained", "submitted", "expired",
                 "overdue", "result", "status", "score", "out of", "/")):
                if len(t) > 3:
                    title = t
                    break
        if title:
            item["title"] = re.sub(r"^\d+\s*[\.\-\)]\s*", "", title).strip()
        else:
            # Last resort — tile header class
            header = pnl.select_one("[class*='tileHeader'], [class*='header']")
            if header:
                t = _normalize(header.get_text())
                t = re.sub(r"^\d+\s*[\.\-\)]\s*", "", t)
                if t:
                    item["title"] = t

        # Extract marks / score (skip text that contains a date)
        marks_numbers: list[str] = []
        other_numbers: list[str] = []
        title_text = item.get("title", "")
        for t in texts:
            if DATE_RE.search(t):
                continue  # skip date-containing text
            if t == title_text:
                continue  # skip the exact title text
            tl = t.lower()
            nums = MARKS_RE.findall(t)
            if "marks" in tl or "total" in tl or "obtained" in tl or "score" in tl:
                marks_numbers.extend(nums)
            else:
                other_numbers.extend(nums)

        def _assign_marks(nums: list[str]) -> bool:
            if len(nums) >= 2:
                item["total_marks"] = nums[-1]
                item["score"] = nums[0]
                try:
                    if float(item["score"]) > float(item["total_marks"]):
                        item["score"], item["total_marks"] = item["total_marks"], item["score"]
                except ValueError:
                    pass
                return True
            elif len(nums) == 1:
                for t in texts:
                    if "out of" in t.lower():
                        parts = MARKS_RE.findall(t)
                        if len(parts) >= 2:
                            item["score"] = parts[0]
                            item["total_marks"] = parts[-1]
                        elif len(parts) == 1:
                            item["total_marks"] = parts[0]
                        return True
                item["total_marks"] = nums[0]
                return True
            return False

        # First try keyword-context numbers, then fallback to bare numbers
        if not _assign_marks(marks_numbers):
            bare = [n for n in other_numbers if re.fullmatch(r"\d+(?:\.\d+)?", n) and len(n) <= 5]
            bare = [n for n in bare if n not in title_text]
            if bare:
                if len(bare) >= 2:
                    item["total_marks"] = bare[-1]
                    item["score"] = bare[0]
                    try:
                        if float(item["score"]) > float(item["total_marks"]):
                            item["score"], item["total_marks"] = item["total_marks"], item["score"]
                    except ValueError:
                        pass
                else:
                    item["total_marks"] = bare[0]

        # Extract panel index
        m = pnl_pat.match(pnl.get("id", ""))
        if m:
            item["_course_index"] = int(m.group(1))

        if item.get("title"):
            items.append(item)

    return items


# ── per-type parsers ─────────────────────────────────────────────────────

def _parse_assignments(
    body_text: str, soup: BeautifulSoup, course_code: str
) -> list[dict]:
    items = _parse_tile_panels(
        soup, "MainContent_gvTileRepeaterAssignment",
        TILE_MAPS["assignments"], course_code,
    )
    if not items:
        items = _parse_fallback_tiles(
            body_text, course_code, "assignment",
        )
    return items


def _parse_quizzes(
    body_text: str, soup: BeautifulSoup, course_code: str
) -> list[dict]:
    items = _parse_tile_panels(
        soup, "MainContent_gvTileRepeaterQuiz",
        TILE_MAPS["quizzes"], course_code,
    )
    if not items:
        items = _parse_tile_by_text(
            soup, "MainContent_gvTileRepeaterQuiz", course_code,
        )
    if not items:
        items = _parse_fallback_tiles(
            body_text, course_code, "quiz",
        )
    return items


def _parse_gdbs(
    body_text: str, soup: BeautifulSoup, course_code: str
) -> list[dict]:
    # lblTitle is stable for GDBs — ID-based first works for core fields
    items = _parse_tile_panels(
        soup, "MainContent_gvTileRepeaterGDB",
        TILE_MAPS["gdbs"], course_code,
    )
    if not items:
        items = _parse_tile_by_text(
            soup, "MainContent_gvTileRepeaterGDB", course_code,
        )
    if not items:
        items = _parse_fallback_tiles(
            body_text, course_code, "gdb",
        )
    return items


def _parse_announcements(
    body_text: str, soup: BeautifulSoup, course_code: str
) -> list[dict]:
    items: list[dict] = []

    # Try accordion-header structure
    for hdr in soup.select("div.accordion-header"):
        spans = hdr.find_all("span")
        texts = [_normalize(s.get_text()) for s in spans if _normalize(s.get_text())]
        item: dict[str, str] = {
            "_course_subject": course_code,
            "_course_index": None,
        }
        if len(texts) >= 1:
            item["title"] = texts[0]
        if len(texts) >= 2:
            item["date"] = texts[1]
        if item.get("title"):
            items.append(item)

    # Try anchor list
    if not items:
        for a in soup.select("a[id*='hpl']"):
            text = _normalize(a.get_text())
            if text and len(text) > 5:
                items.append({
                    "title": text,
                    "_course_subject": course_code,
                    "_course_index": None,
                })

    # Fallback: scan body text for Title + Date pairs
    if not items:
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        i = 0
        while i < len(lines) - 1:
            line = lines[i]
            if line in ("Home", "Back", "Course Announcement", "Assignment") or len(line) < 10:
                i += 1
                continue
            dm = re.match(r"([A-Z][a-z]{2}\s+\d{1,2},?\s*\d{4})$", lines[i + 1]) if i + 1 < len(lines) else None
            if dm:
                items.append({
                    "title": line,
                    "date": dm.group(1),
                    "_course_subject": course_code,
                    "_course_index": None,
                })
                i += 2
                continue
            i += 1

    return items


# ── fallback text-based parser ───────────────────────────────────────────

def _parse_fallback_tiles(
    body_text: str, course_code: str, content_type_label: str
) -> list[dict]:
    """
    Last resort: parse data from body text when tile panels aren't found.
    Handles the tabular layout that some VULMS pages show.
    """
    items: list[dict] = []
    lines = [l.strip() for l in body_text.split("\n") if l.strip()]
    in_table = False

    for line in lines:
        if any(kw in line.lower() for kw in ["sr. no.", "#", "title", "start date"]):
            in_table = True
            continue
        if not in_table:
            continue
        if line in ("Back", "Home", "Help") or len(line) < 3:
            continue
        if not re.match(r"^\d+", line):
            continue

        cols = line.split("\t") if "\t" in line else line.split()
        cols = [c for c in cols if c]
        if len(cols) < 3:
            continue

        item: dict[str, str] = {
            "_course_subject": course_code,
            "_course_index": None,
        }

        if content_type_label in ("quiz", "gdb"):
            item["title"] = cols[1]
        else:
            item["title"] = cols[1] if len(cols) > 1 else cols[0]

        for c in cols:
            dm = re.search(r"([A-Z][a-z]{2}\s+\d{1,2},?\s*\d{4})", c)
            if dm:
                if "start_date" not in item:
                    item["start_date"] = dm.group(1)
                elif "due_date" not in item:
                    item["due_date"] = dm.group(1)

        for c in cols:
            if c in ("Submitted", "Expired", "Not Submitted", "Overdue", "Result Declared"):
                item["status"] = c

        if item.get("title") and item["title"] not in ("-", ""):
            items.append(item)

    return items


# ── main scraping function ───────────────────────────────────────────────

PARSERS = {
    "assignments": _parse_assignments,
    "quizzes": _parse_quizzes,
    "gdbs": _parse_gdbs,
    "announcements": _parse_announcements,
}


def scrape_all_courses(
    driver,
    lms_url: str,
    content_type: str,
) -> list[list]:
    """
    For each course on the home page, click the content button, scrape items,
    then go back to home. Returns a list of item-lists (one per course).
    """
    parser = PARSERS.get(content_type)
    if not parser:
        raise ValueError(f"Unknown content type: {content_type}")

    btn_id_tpl = BUTTON_ID_TEMPLATES.get(content_type)
    if not btn_id_tpl:
        raise ValueError(f"No button template for: {content_type}")

    try:
        home_url = lms_url.rstrip("/") + "/Home.aspx"
        driver.get(home_url)
        time.sleep(3)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as exc:
        raise RuntimeError(f"Could not load home page: {exc}")

    course_count = _get_course_count(driver)
    logger.info("Found %d courses for %s", course_count, content_type)

    all_results: list[list] = []
    current_home_url = driver.current_url

    for i in range(course_count):
        if i > 0:
            try:
                driver.get(current_home_url)
                time.sleep(3)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                pass

        btn_id = btn_id_tpl.format(idx=i)
        logger.info(
            "Processing course %d/%d - clicking %s",
            i + 1, course_count, btn_id,
        )

        clicked = _click_button(driver, btn_id)
        course_items: list[dict] = []

        if clicked:
            time.sleep(2)
            body = driver.find_element(By.TAG_NAME, "body")
            body_text = body.text
            soup = BeautifulSoup(driver.page_source, "html.parser")
            course_code = _extract_course_code(body_text)
            logger.info("  Course code: %s", course_code)

            course_items = parser(body_text, soup, course_code)
            for item in course_items:
                item.setdefault("_course_subject", course_code)
                if item.get("_course_index") is None:
                    item["_course_index"] = i

            logger.info("  => %d items found", len(course_items))
        else:
            logger.warning("  Course %d: button not clickable", i)

        all_results.append(course_items)

    try:
        driver.get(current_home_url)
        time.sleep(2)
    except Exception:
        pass

    return all_results

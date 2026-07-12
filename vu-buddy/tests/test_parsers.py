"""Unit tests for the VULMS tile parsers — works offline with mock HTML."""

from __future__ import annotations

from bs4 import BeautifulSoup
import pytest

from lms_nav import _parse_tile_by_text, _parse_tile_panels, TILE_MAPS


# ── helpers ──────────────────────────────────────────────────────────────

def _make_quiz_html(panel_id_suffix: str, suffix: str) -> str:
    """Build a quiz tile panel with the given span-ID suffix pattern."""
    return f"""
<div id="MainContent_gvTileRepeaterQuiz_pnl_{panel_id_suffix}">
  <span id="MainContent_gvTileRepeaterQuiz_{suffix}Title_{panel_id_suffix}">Quiz 1 — Midterm</span>
  <span id="MainContent_gvTileRepeaterQuiz_{suffix}StartDate_{panel_id_suffix}">Jun 10, 2026</span>
  <span id="MainContent_gvTileRepeaterQuiz_{suffix}EndDate_{panel_id_suffix}">Jun 15, 2026</span>
  <span id="MainContent_gvTileRepeaterQuiz_{suffix}TotalMarks_{panel_id_suffix}">10</span>
  <span id="MainContent_gvTileRepeaterQuiz_{suffix}Status_{panel_id_suffix}">Submitted</span>
  <span id="MainContent_gvTileRepeaterQuiz_{suffix}GetMarks_{panel_id_suffix}">7.50</span>
</div>
"""


def _make_gdb_html() -> str:
    return """
<div id="MainContent_gvTileRepeaterGDB_pnl_0">
  <span id="MainContent_gvTileRepeaterGDB_lblTitle_0">GDB 1 — Discussion Topic</span>
  <span id="MainContent_gvTileRepeaterGDB_Label4_0">Jun 20, 2026</span>
  <span id="MainContent_gvTileRepeaterGDB_Label3_0">Jun 25, 2026</span>
  <span id="MainContent_gvTileRepeaterGDB_Label9_0">5</span>
  <span id="MainContent_gvTileRepeaterGDB_lblStatus_0">Submitted</span>
  <span id="MainContent_gvTileRepeaterGDB_lblMarksObtained_0">4.00</span>
  <span id="MainContent_gvTileRepeaterGDB_lblSubmissionStatus_0">Graded</span>
</div>
"""


# ── Quiz tests ───────────────────────────────────────────────────────────

def test_quiz_with_known_ids():
    """Quizzes with known span IDs (lblTitle etc.) — should work via _parse_tile_panels."""
    html = _make_quiz_html("0", "lbl")
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_tile_panels(
        soup, "MainContent_gvTileRepeaterQuiz",
        TILE_MAPS["quizzes"], "CS101",
    )
    assert len(items) == 1
    assert items[0]["title"] == "Quiz 1 — Midterm"
    assert items[0]["start_date"] == "Jun 10, 2026"
    assert items[0]["due_date"] == "Jun 15, 2026"
    assert items[0]["total_marks"] == "10"
    assert items[0]["status"] == "Submitted"
    assert items[0]["score"] == "7.50"


def test_quiz_with_unknown_ids():
    """Quizzes where span IDs don't match the known map — must use text-based parser."""
    html = _make_quiz_html("0", "Label")  # Label IDs like LabelTitle_0 etc.
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_tile_by_text(soup, "MainContent_gvTileRepeaterQuiz", "CS101")
    assert len(items) == 1
    assert items[0]["title"] == "Quiz 1 — Midterm"
    assert items[0]["start_date"] == "Jun 10, 2026"
    assert items[0]["due_date"] == "Jun 15, 2026"
    assert items[0]["total_marks"] == "10"
    assert items[0]["score"] == "7.50"
    assert items[0]["status"] == "Submitted"


def test_quiz_multiple_panels():
    html = (
        _make_quiz_html("0", "lbl")
        + _make_quiz_html("1", "lbl").replace("Quiz 1", "Quiz 2")
    )
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_tile_by_text(soup, "MainContent_gvTileRepeaterQuiz", "CS101")
    assert len(items) == 2
    titles = [it["title"] for it in items]
    assert any("Quiz 1" in t for t in titles)
    assert any("Quiz 2" in t for t in titles)


# ── GDB tests ────────────────────────────────────────────────────────────

def test_gdb_with_known_ids():
    """GDBs with *known* span IDs (the current fragile map) — verify it parses."""
    html = _make_gdb_html()
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_tile_panels(
        soup, "MainContent_gvTileRepeaterGDB",
        TILE_MAPS["gdbs"], "CS101",
    )
    assert len(items) == 1
    assert items[0]["title"] == "GDB 1 — Discussion Topic"
    assert items[0]["start_date"] == "Jun 20, 2026"
    assert items[0]["due_date"] == "Jun 25, 2026"
    assert items[0]["total_marks"] == "5"
    assert items[0]["status"] == "Submitted"
    assert items[0]["score"] == "4.00"
    assert items[0]["submission_status"] == "Graded"


def test_gdb_with_unknown_ids():
    """GDBs with completely different span IDs — text-based parser must handle it."""
    html = """
<div id="MainContent_gvTileRepeaterGDB_pnl_0">
  <span>GDB 1 — Discussion Topic</span>
  <span>Start Date: Jun 20, 2026</span>
  <span>Due Date: Jun 25, 2026</span>
  <span>Total Marks: 5</span>
  <span>Status: Submitted</span>
  <span>Obtained Marks: 4.00</span>
</div>
"""
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_tile_by_text(soup, "MainContent_gvTileRepeaterGDB", "CS101")
    assert len(items) == 1
    assert items[0]["title"] == "GDB 1 — Discussion Topic"
    assert items[0]["start_date"] == "Jun 20, 2026"
    assert items[0]["due_date"] == "Jun 25, 2026"
    assert items[0]["total_marks"] == "5"
    assert items[0]["score"] == "4.00"
    assert items[0]["status"] == "Submitted"


# ── Edge cases ───────────────────────────────────────────────────────────

def test_empty():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    items = _parse_tile_by_text(soup, "MainContent_gvTileRepeaterQuiz", "CS101")
    assert items == []


def test_panel_with_no_data():
    html = """
<div id="MainContent_gvTileRepeaterQuiz_pnl_0">
  <span id="mylbl_0">-</span>
</div>
"""
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_tile_by_text(soup, "MainContent_gvTileRepeaterQuiz", "CS101")
    # Should not include panels that have no meaningful title
    assert items == []


def test_panel_only_title():
    html = """
<div id="MainContent_gvTileRepeaterQuiz_pnl_0">
  <span id="mylbl_Title_0">Quiz 3</span>
</div>
"""
    soup = BeautifulSoup(html, "html.parser")
    items = _parse_tile_by_text(soup, "MainContent_gvTileRepeaterQuiz", "CS101")
    assert len(items) == 1
    assert items[0]["title"] == "Quiz 3"


def test_status_keywords():
    for kw in ("Expired", "Overdue", "Result Declared", "Not Submitted", "Attempted"):
        html = f"""
<div id="MainContent_gvTileRepeaterQuiz_pnl_0">
  <span>Quiz X</span>
  <span>Status: {kw}</span>
</div>
"""
        soup = BeautifulSoup(html, "html.parser")
        items = _parse_tile_by_text(soup, "MainContent_gvTileRepeaterQuiz", "CS101")
        assert len(items) == 1
        assert items[0]["status"] == kw, f"Failed for status keyword: {kw}"

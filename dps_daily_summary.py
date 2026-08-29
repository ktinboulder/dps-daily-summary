#!/usr/bin/env python3
"""
DPS Weekly School Summary
─────────────────────────
Logs into the Denver Public Schools parent portal (portal.dpsk12.org),
extracts missing assignments, current grades, absences, and upcoming
assignments for each configured student, then emails a formatted HTML summary.

Run:    python dps_daily_summary.py
"""

import asyncio
import html as html_mod
import os
import sys
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date

# ── Optional dependency: python-dotenv ────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# ── Required dependency: playwright ───────────────────────────────────────────
try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright not installed.")
    print("Fix:   pip install playwright && playwright install chromium")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────
DPS_USERNAME     = os.getenv("DPS_USERNAME",      "")
DPS_PASSWORD     = os.getenv("DPS_PASSWORD",      "")
GMAIL_EMAIL      = os.getenv("GMAIL_EMAIL",       "")
GMAIL_APP_PW     = os.getenv("GMAIL_APP_PASSWORD","")
RECIPIENT_EMAILS = [e.strip() for e in os.getenv("RECIPIENT_EMAIL", "").split(",") if e.strip()]


def _load_students() -> list:
    """Build student list from STUDENT_N_* env vars, falling back to legacy single-student vars."""
    students = []
    i = 1
    while True:
        name = os.getenv(f"STUDENT_{i}_NAME", "").strip()
        if not name:
            break
        extra = [e.strip() for e in os.getenv(f"STUDENT_{i}_RECIPIENTS", "").split(",") if e.strip()]
        students.append({
            "name":       name,
            "target":     os.getenv(f"STUDENT_{i}_TARGET_NAME", "").strip(),
            "school":     os.getenv(f"STUDENT_{i}_SCHOOL", "").strip(),
            "grade":      os.getenv(f"STUDENT_{i}_GRADE",  "").strip(),
            "recipients": extra,
        })
        i += 1
    if not students:
        # Legacy single-student config
        students.append({
            "name":       os.getenv("STUDENT_NAME", "Student").strip(),
            "target":     os.getenv("STUDENT_TARGET_NAME", "").strip(),
            "school":     "",
            "grade":      "",
            "recipients": [],
        })
    return students

STUDENTS = _load_students()

# ── Portal URLs ───────────────────────────────────────────────────────────────
BASE     = "https://portal.dpsk12.org/group/parent-portal"
HOME_URL = BASE
ATT_URL  = BASE + "/check-attendance-details"


# ── Login helper ──────────────────────────────────────────────────────────────
async def _login(page) -> None:
    await page.goto("https://portal.dpsk12.org/", wait_until="networkidle")
    await page.click("text=Sign In")
    await page.wait_for_load_state("networkidle")
    await page.fill("#userNameInput", DPS_USERNAME.strip())
    await page.fill("#passwordInput", DPS_PASSWORD.strip())
    await page.click("#submitButton")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(3000)
    if "adfs" in page.url:
        raise RuntimeError("Login failed — check DPS_USERNAME / DPS_PASSWORD in your .env")


async def _switch_portal_student(page, target_name: str) -> None:
    """Switch the portal to the given student if a switcher is present."""
    if not target_name:
        return
    try:
        body_text = await page.inner_text("body")
        if target_name in body_text:
            return
        btns = await page.query_selector_all("button, a[role='tab'], .student-name")
        for btn in btns[:10]:
            txt = (await btn.inner_text()).strip()
            if txt and target_name.split()[0] in txt:
                await btn.click()
                await page.wait_for_timeout(2000)
                return
    except Exception:
        pass


# ── IC assignment text parsers ────────────────────────────────────────────────
def _parse_ic_assignments(text: str, min_date, max_date, exclude_batch_date=None) -> list:
    """Parse IC assignment-list page text into a list of dicts filtered by date range."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    results = []
    current_date = None
    i = 0
    while i < len(lines):
        line = lines[i]
        date_m = re.match(
            r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2}/\d{1,2}/\d{4})',
            line
        )
        if date_m:
            try:
                current_date = datetime.strptime(date_m.group(1), "%m/%d/%Y").date()
            except ValueError:
                pass
        elif line == 'Assignment' and current_date:
            in_range = True
            if min_date and current_date < min_date:
                in_range = False
            if max_date and current_date > max_date:
                in_range = False
            if exclude_batch_date and current_date == exclude_batch_date:
                in_range = False
            if in_range and i + 2 < len(lines):
                name   = lines[i + 1]
                course = lines[i + 2]
                if not course.startswith('Score') and not course.startswith('Assignment') \
                        and not course.startswith('Comments') and not course.startswith('TODAY'):
                    results.append({
                        "course":     course,
                        "assignment": name,
                        "due":        current_date.strftime("%m/%d/%Y"),
                    })
        i += 1
    seen = set()
    unique = []
    for r in results:
        key = (r["due"], r["assignment"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _parse_ic_missing_flagged(text: str, min_date=None) -> list:
    """Extract assignments explicitly marked MISSING in IC."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    results = []
    current_date = None
    i = 0
    while i < len(lines):
        line = lines[i]
        date_m = re.match(
            r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2}/\d{1,2}/\d{4})',
            line
        )
        if date_m:
            try:
                current_date = datetime.strptime(date_m.group(1), "%m/%d/%Y").date()
            except ValueError:
                pass
        elif line == 'Assignment' and current_date and i + 2 < len(lines):
            if min_date and current_date < min_date:
                i += 1
                continue
            name   = lines[i + 1]
            course = lines[i + 2]
            window = lines[i:min(i+6, len(lines))]
            if 'MISSING' in window and not course.startswith('Score') \
                    and not course.startswith('Assignment'):
                results.append({
                    "course":     course,
                    "assignment": name,
                    "due":        current_date.strftime("%m/%d/%Y"),
                })
        i += 1
    return results


# ── Per-student scraper ───────────────────────────────────────────────────────
async def _scrape_student(page, student: dict) -> dict:
    """Scrape all data for one student using an already-authenticated page."""
    result = {
        "student_name":         student["name"],
        "student_school":       student.get("school", ""),
        "student_grade":        student.get("grade", ""),
        "student_recipients":   student.get("recipients", []),
        "date":                 datetime.now().strftime("%A, %B %d, %Y"),
        "gpa":                  "",
        "grades":               [],
        "missing_assignments":  [],
        "absences":             [],
        "attendance_rate":      "",
        "upcoming_assignments": [],
        "error":                None,
    }
    target = student.get("target", "")

    try:
        # ── 1. Home page — grades + missing-assignment counts ──────────────────
        print(f"  → Reading home page (grades & missing assignments)…")
        await page.goto(HOME_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await _switch_portal_student(page, target)

        body = await page.inner_text("body")

        s2_start = None
        s2_m = re.search(r'S2\s+(\d{1,2}/\d{1,2}/\d{4})', body)
        if s2_m:
            try:
                s2_start = datetime.strptime(s2_m.group(1), "%m/%d/%Y").date()
            except ValueError:
                pass

        gpa_m = re.search(r"([\d.]+)\s*GPA", body)
        if gpa_m:
            result["gpa"] = gpa_m.group(1)

        rows = await page.query_selector_all(".tile-contentRowPerformance")
        for row in rows:
            name_el = await row.query_selector(".gradeColDetails .courseDetails b")
            if not name_el:
                continue
            course_name = (await name_el.inner_text()).strip()

            if "Embedded Honors" in course_name:
                continue

            grade_el = await row.query_selector(".gradeCol h3")
            grade = (await grade_el.inner_text()).strip().lstrip("-") if grade_el else ""
            if not grade or grade == "N/A":
                continue

            pct_el = await row.query_selector(".gradeCol p")
            pct = (await pct_el.inner_text()).strip() if pct_el else ""

            detail_el = await row.query_selector(".gradeColDetails .courseDetails")
            full_text = (await detail_el.inner_text()).strip() if detail_el else course_name
            id_m = re.search(r"\((\d{5}-\d+)\)", full_text)
            course_key = f"{course_name} ({id_m.group(1)})" if id_m else course_name

            result["grades"].append({"course": course_key, "grade": grade, "pct": pct})

            miss_el = await row.query_selector("span[class*='missing'], span[aria-label*='missing']")
            if not miss_el:
                row_text = await row.inner_text()
                miss_m = re.search(r"(\d+)\s+missing assignment", row_text)
                if miss_m:
                    count = int(miss_m.group(1))
                    for _ in range(count):
                        result["missing_assignments"].append(
                            {"course": course_key, "assignment": "(see gradebook)", "due": ""}
                        )
            else:
                result["missing_assignments"].append(
                    {"course": course_key, "assignment": "(see gradebook)", "due": ""}
                )

        # ── 2. IC Assignments — missing + upcoming ─────────────────────────────
        print(f"  → Reading Infinite Campus for missing & upcoming assignments…")
        today = date.today()
        LAST_DAY_OF_SCHOOL = date(today.year, 5, 30)
        UPCOMING_WINDOW = today.toordinal() + 45

        try:
            await page.goto("https://campus.dpsk12.org/campus/icprod.jsp", wait_until="networkidle")
            await page.wait_for_timeout(5000)
            await page.click("text=Assignments", timeout=8000)
            await page.wait_for_timeout(5000)

            frames = page.frames
            app_frame = next((f for f in frames if "apps/portal/parent" in f.url), None)

            if app_frame:
                # Switch to target student if needed
                page_text = await app_frame.inner_text("body")
                if target and target not in page_text:
                    try:
                        btns = await app_frame.query_selector_all("button, [tabindex='0']")
                        for btn in btns[:5]:
                            txt = (await btn.inner_text()).strip()
                            if txt and len(txt) > 3 and "Skip" not in txt:
                                await btn.click()
                                await app_frame.wait_for_timeout(1000)
                                break
                    except Exception:
                        pass
                    try:
                        await app_frame.click(f"text={target}", timeout=4000)
                        await app_frame.wait_for_timeout(3000)
                    except Exception:
                        pass

                await app_frame.click("text=Missing")
                await app_frame.wait_for_timeout(2000)
                missing_text = await app_frame.inner_text("body")

                missing_detail = _parse_ic_assignments(missing_text, min_date=s2_start, max_date=today)
                missing_raw = _parse_ic_missing_flagged(missing_text, min_date=s2_start)
                if missing_raw:
                    missing_detail = missing_raw
                if missing_detail:
                    result["missing_assignments"] = missing_detail

                await app_frame.click("text=Missing")
                await app_frame.wait_for_timeout(1000)
                await app_frame.click("text=Current Term")
                await app_frame.wait_for_timeout(3000)
                for _ in range(3):
                    await app_frame.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await app_frame.wait_for_timeout(2000)
                current_text = await app_frame.inner_text("body")

                upcoming_detail = _parse_ic_assignments(
                    current_text,
                    min_date=today,
                    max_date=date.fromordinal(UPCOMING_WINDOW),
                    exclude_batch_date=LAST_DAY_OF_SCHOOL,
                )
                if upcoming_detail:
                    result["upcoming_assignments"] = sorted(upcoming_detail, key=lambda x: x["due"])

        except Exception as e:
            print(f"   ⚠ IC assignments fetch failed: {e}")

        # ── 3. Attendance page ─────────────────────────────────────────────────
        print(f"  → Reading attendance…")
        await page.goto(ATT_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await _switch_portal_student(page, target)

        att_body = await page.inner_text("body")

        rate_m = re.search(r"([\d.]+%)[^\n]*\d+\.?\d*/\d+\.?\d*\s*days", att_body)
        if rate_m:
            result["attendance_rate"] = rate_m.group(1)

        att_pattern = re.compile(
            r"([A-Za-z][^\n]+?\(\d{5}-\d+\))\nTeacher:[^\n]+\n(\d+)\n(\d+)",
        )
        for m in att_pattern.finditer(att_body):
            course   = m.group(1).strip()
            absences = int(m.group(2))
            tardies  = int(m.group(3))
            if "Embedded Honors" in course:
                continue
            if absences > 0 or tardies > 0:
                result["absences"].append({
                    "course":   course,
                    "absences": absences,
                    "tardies":  tardies,
                })

    except Exception as e:
        result["error"] = str(e)
        print(f"   ✗ Error: {e}")

    return result


# ── Main scraper (manages browser lifecycle) ───────────────────────────────────
async def scrape_all_students() -> list:
    """Login once, then scrape each student sequentially with the same session."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        page.set_default_timeout(25_000)

        results = []
        try:
            print("→ Logging in…")
            await _login(page)
            print("→ Login successful.")

            for student in STUDENTS:
                print(f"\n── {student['name']} ────────────────────────────")
                data = await _scrape_student(page, student)
                results.append(data)

        finally:
            await browser.close()

    return results


# ── HTML email builder ────────────────────────────────────────────────────────
def build_email_html(data: dict) -> str:
    date_str = html_mod.escape(data.get("date", datetime.now().strftime("%A, %B %d, %Y")))
    student  = html_mod.escape(data.get("student_name", "Your Child"))
    school   = html_mod.escape(data.get("student_school", ""))
    grade    = html_mod.escape(data.get("student_grade", ""))
    gpa      = html_mod.escape(data.get("gpa", ""))
    error    = html_mod.escape(data.get("error") or "") or None

    school_line = ""
    if school or grade:
        parts = [p for p in [school, f"Grade {grade}" if grade else ""] if p]
        school_line = f'<div style="opacity:0.75;font-size:13px;margin-top:3px;">{" · ".join(parts)}</div>'

    # ── Missing assignments section
    missing = data.get("missing_assignments", [])
    if missing:
        miss_rows = "".join(
            f'<tr style="border-bottom:1px solid #fecaca;">'
            f'<td style="padding:8px 12px;font-size:13px;color:#991b1b;">{html_mod.escape(a["assignment"])}</td>'
            f'<td style="padding:8px 12px;font-size:13px;color:#6b7280;">{html_mod.escape(_short_course(a["course"]))}</td>'
            f'<td style="padding:8px 12px;font-size:13px;color:#6b7280;white-space:nowrap;">{html_mod.escape(a["due"])}</td>'
            f'</tr>'
            for a in missing
        )
        miss_html = f"""
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="background:#fef2f2;">
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#991b1b;border-bottom:2px solid #fecaca;">ASSIGNMENT</th>
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#991b1b;border-bottom:2px solid #fecaca;">CLASS</th>
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#991b1b;border-bottom:2px solid #fecaca;">DUE</th>
            </tr>
          </thead>
          <tbody>{miss_rows}</tbody>
        </table>"""
    else:
        miss_html = '<p style="color:#16a34a;font-style:italic;margin:6px 0;">✓ No missing assignments</p>'

    miss_count = len(missing)
    miss_color = "#dc2626" if miss_count else "#16a34a"
    miss_bg    = "#fee2e2" if miss_count else "#dcfce7"
    miss_icon  = "⚠️" if miss_count else "✅"

    # ── Grades section
    grades = data.get("grades", [])
    if grades:
        grade_rows = "".join(
            f'<tr style="border-bottom:1px solid #f3f4f6;">'
            f'<td style="padding:8px 12px;font-size:13px;">{html_mod.escape(_short_course(g["course"]))}</td>'
            f'<td style="padding:8px 12px;font-size:14px;font-weight:700;text-align:center;'
            f'color:{_grade_color(g["grade"])};">{html_mod.escape(g["grade"])}</td>'
            f'<td style="padding:8px 12px;font-size:13px;text-align:right;color:#6b7280;">{html_mod.escape(g["pct"])}</td>'
            f'</tr>'
            for g in grades
        )
        grades_html = f"""
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="background:#f8fafc;">
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">COURSE</th>
              <th style="padding:7px 12px;text-align:center;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">GRADE</th>
              <th style="padding:7px 12px;text-align:right;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">%</th>
            </tr>
          </thead>
          <tbody>{grade_rows}</tbody>
        </table>"""
    else:
        grades_html = '<p style="color:#6b7280;font-style:italic;">No grade data found</p>'

    # ── Absences section
    absences = data.get("absences", [])
    att_rate  = data.get("attendance_rate", "")
    if absences:
        abs_rows = "".join(
            f'<tr style="border-bottom:1px solid #f3f4f6;">'
            f'<td style="padding:7px 12px;font-size:13px;">{html_mod.escape(_short_course(a["course"]))}</td>'
            f'<td style="padding:7px 12px;font-size:13px;text-align:center;'
            f'color:{"#dc2626" if a["absences"]>2 else "#d97706" if a["absences"]>0 else "#16a34a"};">'
            f'{a["absences"]}</td>'
            f'<td style="padding:7px 12px;font-size:13px;text-align:center;color:#6b7280;">{a["tardies"]}</td>'
            f'</tr>'
            for a in absences
        )
        abs_html = f"""
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="background:#f8fafc;">
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">COURSE</th>
              <th style="padding:7px 12px;text-align:center;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">ABSENCES</th>
              <th style="padding:7px 12px;text-align:center;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">TARDIES</th>
            </tr>
          </thead>
          <tbody>{abs_rows}</tbody>
        </table>"""
    else:
        abs_html = '<p style="color:#16a34a;font-style:italic;margin:6px 0;">✓ No absences this semester</p>'

    # ── Upcoming assignments section
    upcoming = data.get("upcoming_assignments", [])
    if upcoming:
        up_rows = "".join(
            f'<tr style="border-bottom:1px solid #f3f4f6;">'
            f'<td style="padding:7px 12px;font-size:13px;">{html_mod.escape(a["assignment"])}</td>'
            f'<td style="padding:7px 12px;font-size:13px;color:#6b7280;">{html_mod.escape(_short_course(a["course"]))}</td>'
            f'<td style="padding:7px 12px;font-size:13px;color:#6b7280;white-space:nowrap;">{html_mod.escape(a["due"])}</td>'
            f'</tr>'
            for a in upcoming
        )
        up_html = f"""
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="background:#f8fafc;">
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">ASSIGNMENT</th>
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">CLASS</th>
              <th style="padding:7px 12px;text-align:left;font-size:12px;color:#6b7280;border-bottom:2px solid #e5e7eb;">DUE</th>
            </tr>
          </thead>
          <tbody>{up_rows}</tbody>
        </table>"""
    else:
        up_html = '<p style="color:#6b7280;font-style:italic;margin:6px 0;">No upcoming assignments in the next 2 weeks</p>'

    error_block = ""
    if error:
        error_block = (
            f'<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:12px 16px;margin:0 0 0;">'
            f'<strong>⚠ Note:</strong> Some data may be incomplete — {error}</div>'
        )

    gpa_block = f'<span style="font-size:13px;opacity:0.85;margin-left:12px;">GPA: {gpa}</span>' if gpa else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:20px;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:620px;margin:0 auto;background:#fff;border-radius:14px;
     overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.10);">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e3a8a,#2563eb);color:#fff;padding:26px 24px;">
    <div style="font-size:24px;font-weight:700;margin-bottom:4px;">📚 Weekly School Summary</div>
    <div style="opacity:0.9;font-size:14px;">{student} · {date_str}{gpa_block}</div>
    {school_line}
  </div>

  {error_block}

  <!-- Missing Assignments -->
  <div style="padding:18px 24px;border-bottom:1px solid #e5e7eb;">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
      <span style="font-size:16px;font-weight:700;color:#111827;">{miss_icon} Missing Assignments</span>
      <span style="background:{miss_bg};color:{miss_color};border-radius:20px;
            padding:2px 10px;font-size:13px;font-weight:700;">{miss_count}</span>
    </div>
    {miss_html}
  </div>

  <!-- Current Grades -->
  <div style="padding:18px 24px;border-bottom:1px solid #e5e7eb;">
    <div style="font-size:16px;font-weight:700;color:#111827;margin-bottom:12px;">📊 Current Grades</div>
    {grades_html}
  </div>

  <!-- Attendance / Absences -->
  <div style="padding:18px 24px;border-bottom:1px solid #e5e7eb;">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
      <span style="font-size:16px;font-weight:700;color:#111827;">🗓️ Absences This Semester</span>
      {"<span style='font-size:13px;color:#6b7280;'>Attendance rate: " + html_mod.escape(att_rate) + "</span>" if att_rate else ""}
    </div>
    {abs_html}
  </div>

  <!-- Upcoming Assignments (next 2 weeks) -->
  <div style="padding:18px 24px;">
    <div style="font-size:16px;font-weight:700;color:#111827;margin-bottom:12px;">📝 Upcoming Assignments <span style="font-size:13px;font-weight:400;color:#6b7280;">(next 14 days)</span></div>
    {up_html}
  </div>

  <!-- Footer -->
  <div style="background:#f8fafc;padding:12px 24px;text-align:center;
       font-size:12px;color:#9ca3af;border-top:1px solid #e5e7eb;">
    Pulled from DPS Parent Portal · {date_str}
  </div>

</div>
</body></html>"""


def _short_course(name: str) -> str:
    """Remove the section code (e.g. ' (01371-11)') for cleaner display."""
    return re.sub(r"\s*\(\d{5}-\d+\)\s*", "", name).strip()


def _grade_color(letter: str) -> str:
    if letter.startswith("A"):  return "#16a34a"
    if letter.startswith("B"):  return "#2563eb"
    if letter.startswith("C"):  return "#d97706"
    return "#dc2626"


# ── Email sender ──────────────────────────────────────────────────────────────
def send_email(html: str, student_name: str, subject_date: str, recipients: list) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📚 Weekly School Summary — {student_name} — {subject_date}"
    msg["From"]    = GMAIL_EMAIL
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))

    print(f"  → Sending email to {', '.join(recipients)}…")
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(GMAIL_EMAIL, GMAIL_APP_PW)
        server.sendmail(GMAIL_EMAIL, recipients, msg.as_string())
    print(f"  → Email sent!")


# ── Entry point ───────────────────────────────────────────────────────────────
async def main() -> None:
    print(f"\n{'='*55}")
    print(f"  DPS Weekly School Summary  ·  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"{'='*55}\n")

    all_data = await scrape_all_students()

    for data in all_data:
        print(f"\n── Results: {data['student_name']} ──────────────────────────")
        print(f"  GPA                 : {data.get('gpa','—')}")
        print(f"  Grades              : {len(data.get('grades', []))} courses")
        print(f"  Missing assignments : {len(data.get('missing_assignments', []))}")
        print(f"  Absences recorded   : {len(data.get('absences', []))} courses with absences")
        print(f"  Upcoming (14 days)  : {len(data.get('upcoming_assignments', []))}")
        print(f"  Attendance rate     : {data.get('attendance_rate','—')}")
        if data.get("error"):
            print(f"  Error               : {data['error']}")

        # Merge global recipients with any student-specific extras (deduplicated)
        extra = data.get("student_recipients", [])
        recipients = list(dict.fromkeys(RECIPIENT_EMAILS + extra))
        html = build_email_html(data)
        send_email(html, data["student_name"], data["date"], recipients)

    print("\n✓ Done!")


if __name__ == "__main__":
    asyncio.run(main())

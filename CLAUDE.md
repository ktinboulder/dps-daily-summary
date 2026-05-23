# DPS Daily School Summary

A Python + Playwright script that logs into the Denver Public Schools Parent Portal (`portal.dpsk12.org`), scrapes school data for a student, and emails a formatted HTML daily summary.

## What It Does

Each run collects and emails:
- **Missing assignments** — per course, with due dates
- **Current grades** — letter grade and percentage for each course
- **Attendance / absences** — courses with absences or tardies this semester
- **Upcoming assignments** — due within the next 45 days

## Project Structure

```
dps_daily_summary.py   # Main script — scrape + email
.env.template          # Copy to .env and fill in credentials
setup.sh               # One-time setup: pip install, playwright, cron
requirements.txt       # Python dependencies
CLAUDE.md              # This file
```

## Setup

1. **Install dependencies**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
   The setup script installs Python packages, downloads the Playwright Chromium browser, copies `.env.template` → `.env`, optionally runs a test, and adds a daily 7 PM cron job.

2. **Fill in `.env`**
   ```
   DPS_USERNAME=your_infinite_campus_username
   DPS_PASSWORD=your_infinite_campus_password
   GMAIL_EMAIL=you@gmail.com
   GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail App Password (not your main password)
   RECIPIENT_EMAIL=you@gmail.com
   STUDENT_NAME=YourChildsName
   ```
   Get a Gmail App Password at: https://myaccount.google.com/security → App passwords

3. **Run manually**
   ```bash
   python3 dps_daily_summary.py
   ```

## Key Architecture Notes

### Authentication
- The portal uses ADFS SSO. Login flow: `portal.dpsk12.org` → click "Sign In" → ADFS form (`#userNameInput`, `#passwordInput`, `#submitButton`).
- After portal login, Infinite Campus (`campus.dpsk12.org`) is accessible via the same session (SAML SSO).

### Grades & Missing Counts (Home Page)
- DOM selector: `.tile-contentRowPerformance` rows on `portal.dpsk12.org/group/parent-portal`
- Skip rows where course name contains "Embedded Honors" (scheduling artifacts, no real grade)
- Letter grade: `.gradeCol h3`, percentage: `.gradeCol p`, course name: `.gradeColDetails .courseDetails b`

### Missing & Upcoming Assignments (Infinite Campus)
- Navigate to `campus.dpsk12.org/campus/icprod.jsp`, click "Assignments"
- Content lives in an **iframe** — find it via `page.frames` matching `apps/portal/parent` in URL
- Multi-student accounts: click the student name button to open the switcher, then click "William B. Taylor"
- IC assignment filters are **toggles** that combine additively:
  - Click "Missing" → shows missing only
  - Deselect "Missing" (click again), then click "Current Term" → shows all current-term assignments
- Scroll 3× to lazy-load future assignments

### Attendance
- Navigate to `portal.dpsk12.org/group/parent-portal/check-attendance-details`
- Regex pattern: `([Course Name (ID)])\nTeacher: ...\n(absences)\n(tardies)`

### Email
- Sent via Gmail SMTP SSL (port 465) using a Gmail App Password
- HTML email with color-coded grade table, red missing-assignments table, attendance table, upcoming table

### Multi-Student Account
- This account has two students: Kathryn R. Taylor (Northfield HS) and William B. Taylor (DSA HS, Grade 09)
- The script targets William B. Taylor — the student-switcher logic handles this automatically

## Dependencies

- `playwright>=1.40.0` — async browser automation
- `python-dotenv>=1.0.0` — loads `.env` credentials
- Playwright Chromium browser (installed separately via `playwright install chromium`)

## Scheduling

The `setup.sh` script adds a cron job:
```
0 19 * * *   python3 /path/to/dps_daily_summary.py >> /path/to/dps_summary.log 2>&1
```
Runs every day at 7:00 PM. The laptop must be awake for cron to fire.

To view or edit the schedule:
```bash
crontab -l       # view
crontab -e       # edit
```

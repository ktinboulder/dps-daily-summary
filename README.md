# DPS Daily School Summary

Quick daily/weekly check-in for your kid's Denver Public Schools grades. Logs in, pulls grades and attendance, and emails a summary to the whole family. No more "how are your classes going?" with mysterious silence as the answer.

## What you get

A daily HTML email with:

- **Current grades** — letter grade and percentage for every class
- **Missing assignments** — what's overdue and which class it's for
- **Attendance** — absences and tardies per class this semester
- **Upcoming assignments** — what's due in the next two weeks

## Requirements

- Python 3.9+
- A DPS Infinite Campus parent portal account
- A Gmail account with an [App Password](https://myaccount.google.com/security) set up

## Setup

```bash
git clone https://github.com/ktinboulder/dps-daily-summary.git
cd dps-daily-summary
chmod +x setup.sh
./setup.sh
```

The setup script installs dependencies, downloads the Playwright browser, and schedules a daily 7 PM cron job.

Then fill in `.env` with your credentials:

```
DPS_USERNAME=your_infinite_campus_username
DPS_PASSWORD=your_infinite_campus_password
GMAIL_EMAIL=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
RECIPIENT_EMAIL=you@gmail.com,spouse@gmail.com

STUDENT_1_NAME=Alex
STUDENT_1_TARGET_NAME=Alex J. Smith
STUDENT_1_SCHOOL=My High School
STUDENT_1_GRADE=11
STUDENT_1_RECIPIENTS=alex@icloud.com
```

- **`RECIPIENT_EMAIL`** — shared recipients who get every student's summary (parents, guardians).
- **`STUDENT_N_TARGET_NAME`** — full name as it appears in the portal switcher. Required on multi-student accounts.
- **`STUDENT_N_RECIPIENTS`** — optional, student-specific extra recipients (e.g. the student themselves). Merged with `RECIPIENT_EMAIL`.
- Get your Gmail App Password at myaccount.google.com → Security → App passwords.

## Run manually

```bash
python3 dps_daily_summary.py
```

## Schedule

The setup script adds a cron job that fires every day at 7 PM. The laptop must be awake for it to run.

```bash
crontab -l    # view schedule
crontab -e    # edit or remove
```

## Multi-student accounts

Add a numbered block for each student. Numbering starts at 1 and must be consecutive:

```
RECIPIENT_EMAIL=you@gmail.com,spouse@gmail.com

STUDENT_1_NAME=Alex
STUDENT_1_TARGET_NAME=Alex J. Smith
STUDENT_1_SCHOOL=East High School
STUDENT_1_GRADE=11
STUDENT_1_RECIPIENTS=alex@icloud.com

STUDENT_2_NAME=Jordan
STUDENT_2_TARGET_NAME=Jordan M. Smith
STUDENT_2_SCHOOL=West Middle School
STUDENT_2_GRADE=8
STUDENT_2_RECIPIENTS=jordan@icloud.com
```

The script logs in once and scrapes each student in sequence. Each student gets their own email — `RECIPIENT_EMAIL` recipients (shared) plus any `STUDENT_N_RECIPIENTS` (student-specific). Siblings don't receive each other's summaries.

## Using with Claude Code

This repo includes a `CLAUDE.md` file that gives Claude Code full context on how the portal works, how the scraper is structured, and where the tricky bits are (SSO flow, iframe navigation, semester filtering, etc.). That means you can open the project in Claude Code and just describe what you want in plain English.

**Install Claude Code** if you haven't already:

```bash
npm install -g @anthropic-ai/claude-code
```

**Open the project:**

```bash
cd dps-daily-summary
claude
```

**Things you can ask Claude Code to do:**

- `Run the daily summary` — executes the script and reports results
- `Add my partner's email to the recipient list` — updates `.env`
- `Only show assignments due in the next 7 days instead of 14` — modifies the upcoming window
- `The login is failing, help me debug it` — investigates and fixes auth issues
- `Email me on Mondays only` — updates the cron schedule
- `Add a section showing GPA trend over the last 4 weeks` — extends the scraper

Claude Code reads `CLAUDE.md` automatically, so it already knows the portal's SSO flow, which iframe the assignments live in, how semester filtering works, and other details that would otherwise take time to figure out from the code.

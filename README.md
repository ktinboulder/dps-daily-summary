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
RECIPIENT_EMAIL=you@gmail.com,spouse@gmail.com,grandma@yahoo.com
STUDENT_NAME=Will
STUDENT_TARGET_NAME=William B. Taylor
```

- **`RECIPIENT_EMAIL`** accepts a comma-separated list — send it to the whole family.
- **`STUDENT_TARGET_NAME`** is the full name as it appears in the portal. Required if your account has multiple students.
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

If your portal account has more than one student, set `STUDENT_TARGET_NAME` to the full name of the student you want — exactly as it appears in the portal switcher. The script will select that student automatically.

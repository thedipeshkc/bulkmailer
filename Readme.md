# BulkMailer — Free Multi-User Bulk Email SaaS

A fully deployed web app where anyone can sign up, connect their free Brevo account, and send personalized bulk emails to thousands of people.

**Live URL:** `dkbulkemail.pythonanywhere.com`

---

## What It Does

BulkMailer lets any user:
- Sign up and create their own private account
- Connect their own free Brevo SMTP credentials
- Upload a CSV file of contacts
- Write a personalized email with `{name}` placeholders
- Add an event image and feedback button
- Preview the email before sending
- Send to everyone and watch live progress
- Save and reuse email templates
- Track full campaign history

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python + Flask |
| Database | SQLite (per-user data) |
| Email sending | Brevo SMTP (free) |
| Frontend | HTML + CSS + Vanilla JS |
| Hosting | PythonAnywhere (free) |
| Code hosting | GitHub |

---

## Folder Structure

```
bulk-email-webapp/
├── app.py                  ← Flask backend, all routes and logic
├── bulkmailer.db           ← SQLite database (auto-created)
├── requirements.txt        ← Python dependencies (flask)
├── Readme.md               ← This file
└── templates/
    ├── login.html          ← Signup and login page
    ├── dashboard.html      ← Main app dashboard
    └── guide.html          ← Brevo setup guide for new users
```

---

## Features

### Multi-User System
- Each user has their own account (signup/login with email + password)
- Passwords are hashed with SHA-256
- Each user's credentials, templates, and history are completely private

### Campaign Wizard (4 steps)
1. **Contacts** — Upload CSV with `name` and `email` columns. Drag and drop supported. Shows preview table of loaded contacts.
2. **Email** — Write subject, body, add image URL and feedback link. Use `{name}` anywhere to personalize each email.
3. **Preview** — See exactly how the email looks before sending.
4. **Send** — Live progress bar, real-time log, sent/failed counters.

### Templates
- Save any email as a reusable template
- Load saved templates into compose screen with one click
- Delete templates you no longer need

### History
- Every campaign is saved with subject, total, sent, failed count, and date
- View last 20 campaigns on the History page

### Settings
- Each user saves their own Brevo SMTP credentials
- Credentials are stored per-user in the database
- Sender name and email customizable per user

### Setup Guide
- Built-in step-by-step guide at `/guide`
- Walks new users through creating a Brevo account and getting credentials
- Share this link with anyone who signs up

---

## How to Run Locally

```bash
pip install flask
python app.py
# Open: http://localhost:5000
```


## Free Limits

| Resource | Free Limit |
|---|---|
| Emails per user per day | 300 (Brevo free plan) |
| Number of users | Unlimited |
| Contacts per campaign | Unlimited |
| Templates per user | Unlimited |
| Hosting | Free on PythonAnywhere |
| PythonAnywhere uptime | Must log in once per month |



## For New Users

Send them this link:
```
dkbulkemail.pythonanywhere.com/guide
```

The guide walks them through getting their Brevo credentials and sending their first campaign.

---

## Built By

Dipesh K C — Morehead State University
Originally built for NSA Nepali Night 2083 feedback collection.
Evolved into a free multi-user bulk email platform.

---

## Future Ideas

- Email open tracking
- Unsubscribe link handling
- Schedule emails for later
- Custom HTML email editor
- Multiple sender emails per user
- Admin panel to manage all users
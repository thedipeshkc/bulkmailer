# BulkMailer — Free Multi-User Bulk Email SaaS
 
A full web app where anyone can sign up, connect their Brevo account, and send bulk emails.
 
## Folder Structure
```
mailer-saas/
├── app.py               ← Flask backend
├── requirements.txt     ← Python dependencies
├── Procfile             ← For Railway deployment
└── templates/
    ├── login.html       ← Signup / Login page
    └── dashboard.html   ← Full dashboard
```
 
## Run Locally
```bash
pip install -r requirements.txt
python app.py
# Open: http://localhost:5000
```

## Features
- Signup / Login (each user has their own account)
- Save Brevo SMTP credentials per user
- Upload CSV contacts
- Write email with {name} personalization
- Add image URL
- Live email preview
- Send with live progress tracking
- Campaign history per user
- Save & reuse email templates
 
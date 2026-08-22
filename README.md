# Job Application Tracker - Django REST Backend

Standalone Django REST Framework API server for the Job Application Tracker featuring automated Gmail OAuth2 syncing, LLM-powered AI job classification (Google Gemini & OpenAI APIs), Celery background task processing, PostgreSQL database support, JWT authentication, Excel/CSV import/export, and Docker containerization.

---

## ⚡ Key Features

- 🤖 **LLM AI Job Classification**: Integrates `AIJobClassifierService` supporting **Google Gemini API** & **OpenAI API** to intelligently analyze incoming Gmail messages, extract application status (`Applied`, `Interview Scheduled`, `Offer`, `Rejected`), company, role, recruiter info, and provide human-readable AI reasoning.
- ⚙️ **Resilient Fallback Parser**: Combines LLM classification with automatic fallback to rule-based regex parsing for high extraction reliability.
- 📧 **Automated Gmail OAuth2 Sync**: Integrates with Google APIs for offline sync with access token auto-refresh and cache locking.
- ⏱️ **Celery Background Sync & GitHub Actions**: Offloads Gmail ingestion tasks to Celery workers with Redis. Supports automated periodic cron synchronization via GitHub Actions or Celery Beat.
- 📊 **Analytics & Summary Endpoints**: Provides application conversion rates, platform breakdown, and monthly application trends.
- 📥 **Excel/CSV Data Import & Export**: Bulk import existing application spreadsheets and export tracking data directly to Excel.

---

## Tech Stack
- **Framework**: Django 5.0+, Django REST Framework
- **AI / LLM Integration**: Google Gemini API (`google-generativeai`), OpenAI API (`openai`)
- **Auth**: JWT Authentication (`djangorestframework-simplejwt`), Google OAuth2 Client
- **Database**: PostgreSQL (Production/Docker) with automatic SQLite fallback (Local Dev)
- **Task Queue & Scheduler**: Celery, Redis, GitHub Actions Cron Sync
- **Data Processing**: pandas, openpyxl
- **Server**: Gunicorn / Uvicorn

---

## Standalone Git Repository Setup

To push this backend directory as its own independent GitHub repository:

```bash
cd job-tracker-backend
git init
git add .
git commit -m "Initial commit: Job Application Tracker Backend"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/job-tracker-backend.git
git push -u origin main
```

---

## Running Locally

### Option 1: Virtual Environment (SQLite Default)
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations & start dev server
python manage.py migrate
python manage.py runserver 8000
```

### Background Gmail Sync Execution
Run periodic Gmail application synchronization without Redis or Celery using the built-in management command:

```bash
# Execute batch Gmail sync across all active users with cache locking
python manage.py sync_gmail
```

#### GitHub Actions Workflow (.github/workflows/scheduled-gmail-sync.yml)
Runs automatically on a configurable schedule or manual trigger (`workflow_dispatch`). Triggers the secured background cron sync endpoint (`POST /api/applications/gmail/cron-sync/`) using `CRON_SECRET`.

---

### Option 2: Celery Worker & Celery Beat (Optional)
If running Redis & Celery in production:

```bash
# Start Redis (if not running)
redis-server

# Run Celery Worker (In terminal 1)
celery -A config worker --loglevel=info

# Run Celery Beat Scheduler (In terminal 2 - handles periodic sync)
celery -A config beat --loglevel=info
```

### Option 3: Docker Compose (Django + PostgreSQL + Redis + Celery)
```bash
docker-compose up --build
```
This automatically starts:
- PostgreSQL database container on port `5432`
- Redis container on port `6379`
- Django Backend container on port `8000`
- Celery Worker container
- Celery Beat container

---

## Environment Variables (.env)

Copy `.env.example` to `.env`:
```env
SECRET_KEY=your-production-secret-key
DEBUG=False
DB_NAME=jobtracker
DB_USER=postgres
DB_PASSWORD=your-postgres-password
DB_HOST=db
DB_PORT=5432
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key
CRON_SECRET=your-cron-secret-token
CORS_ALLOWED_ORIGINS=https://jobtracker-7aq.pages.dev,http://localhost:5173
```

---

## API Endpoints

### Authentication & User Profile
- `POST /api/accounts/register/` - User registration
- `POST /api/accounts/login/` - User login (JWT obtain)
- `POST /api/accounts/token/refresh/` - Refresh JWT token
- `GET /api/accounts/profile/` - User profile

### Job Applications & Dashboard
- `GET /api/dashboard/` - Summary metrics card data
- `GET /api/applications/` - List applications (supports `search`, `status`, `platform`, `ordering`)
- `POST /api/applications/` - Create application record
- `PUT/PATCH /api/applications/{id}/` - Update record
- `DELETE /api/applications/{id}/` - Delete record
- `POST /api/applications/import/` - Import CSV / Excel file
- `GET /api/applications/export/` - Download Excel spreadsheet
- `GET /api/analytics/` - Analytics breakdown metrics

### Gmail Integration & AI Sync
- `GET /api/applications/gmail/auth-url/` - Get Google OAuth authorization URL
- `POST /api/applications/gmail/connect/` - Exchange Google OAuth code / store credentials
- `GET /api/applications/gmail/status/` - Connection status & last synced timestamp
- `POST /api/applications/gmail/sync/` - Offload Gmail sync task to Celery background worker
- `POST /api/applications/gmail/cron-sync/` - Internal API endpoint for automated cron synchronization (`CRON_SECRET`)
- `POST /api/applications/gmail/disconnect/` - Disconnect Gmail integration
- `GET /api/applications/gmail/messages/` - Review staged emails queue (returns AI reasoning & extraction source)
- `POST /api/applications/gmail/emails/{id}/approve/` - Approve staged email into Application record
- `POST /api/applications/gmail/emails/bulk-approve/` - Bulk approve staged emails
- `POST /api/applications/gmail/emails/{id}/ignore/` - Mark email as ignored
- `POST /api/applications/gmail/emails/bulk-ignore/` - Bulk mark emails as ignored

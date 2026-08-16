# Job Application Tracker - Django REST Backend

Standalone Django REST Framework API server for the Job Application Tracker featuring automated Gmail syncing, Celery background tasks, Celery Beat 24-hour periodic scheduling, PostgreSQL database support, JWT authentication, Excel/CSV import/export, and Docker containerization.

---

## Tech Stack
- **Framework**: Django 5.0+, Django REST Framework
- **Auth**: JWT Authentication (`djangorestframework-simplejwt`)
- **Database**: PostgreSQL (Production/Docker) with automatic SQLite fallback (Local Dev)
- **Task Queue & Scheduler**: Celery, Redis, Celery Beat (24-hour periodic sync)
- **Third-Party Integration**: Google Gmail API (OAuth2, Email parsing & LLM/NLP job extraction)
- **Data Processing**: pandas, openpyxl
- **Server**: Gunicorn, Uvicorn / WSGI

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

### Celery Worker & Celery Beat (Background Sync)
To process asynchronous Gmail sync tasks and 24-hour scheduled background syncs:

```bash
# Start Redis (if not running)
redis-server

# Run Celery Worker (In terminal 1)
celery -A config worker --loglevel=info

# Run Celery Beat Scheduler (In terminal 2 - handles 24hr background sync)
celery -A config beat --loglevel=info
```

### Option 2: Docker Compose (Django + PostgreSQL + Redis + Celery + Celery Beat)
```bash
docker-compose up --build
```
This automatically starts:
- PostgreSQL database container on port `5432`
- Redis container on port `6379`
- Django Backend container on port `8000`
- Celery Worker container
- Celery Beat container (24-hour periodic sync scheduler)

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
CORS_ALLOWED_ORIGINS=https://yourusername.github.io,http://localhost:5173
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
- `DELETE /api/applications/{id}/` - Delete record (unlocks/resets staged email status if linked)
- `POST /api/applications/import/` - Import CSV / Excel file
- `GET /api/applications/export/` - Download Excel spreadsheet
- `GET /api/analytics/` - Analytics breakdown metrics

### Gmail Integration & Async Sync
- `GET /api/applications/gmail/auth-url/` - Get Google OAuth authorization URL
- `POST /api/applications/gmail/connect/` - Exchange Google OAuth code / store credentials
- `GET /api/applications/gmail/status/` - Connection status & last synced timestamp
- `POST /api/applications/gmail/sync/` - Offload Gmail sync task to Celery worker queue (returns `task_id`)
- `POST /api/applications/gmail/disconnect/` - Disconnect Gmail integration
- `GET /api/applications/gmail/messages/` - Review staged emails queue (filter by `status`, `is_job_related`, `search`)
- `POST /api/applications/gmail/emails/{id}/approve/` - Approve staged email into Application record
- `POST /api/applications/gmail/emails/bulk-approve/` - Bulk approve staged emails
- `POST /api/applications/gmail/emails/{id}/ignore/` - Mark email as ignored
- `POST /api/applications/gmail/emails/bulk-ignore/` - Bulk mark emails as ignored


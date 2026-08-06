# Job Application Tracker - Django REST Backend

Standalone Django REST Framework API server for the Job Application Tracker with PostgreSQL database support, JWT authentication, Excel/CSV import/export, and Docker containerization.

---

## Tech Stack
- **Framework**: Django 5.0+, Django REST Framework
- **Auth**: JWT Authentication (`djangorestframework-simplejwt`)
- **Database**: PostgreSQL (Production/Docker) with automatic SQLite fallback (Local Dev)
- **Data Processing**: pandas, openpyxl
- **Server**: Gunicorn, Uvicorn / WSGI

---

## Standalone Git Repository Setup

To push this backend directory as its own independent GitHub repository:

```bash
cd backend
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
# Create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations & start dev server
python manage.py migrate
python manage.py runserver 8000
```

### Option 2: Docker Compose (Django + PostgreSQL)
```bash
docker-compose up --build
```
This automatically starts:
- PostgreSQL database container on port `5432`
- Django Backend container on port `8000`

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
CORS_ALLOWED_ORIGINS=https://yourusername.github.io,http://localhost:5173
```

---

## API Endpoints

- `POST /api/accounts/register/` - User registration
- `POST /api/accounts/login/` - User login (JWT obtain)
- `POST /api/accounts/token/refresh/` - Refresh JWT token
- `GET /api/accounts/profile/` - User profile
- `GET /api/dashboard/` - Summary metrics card data
- `GET /api/applications/` - List applications (supports `search`, `status`, `platform`, `ordering`)
- `POST /api/applications/` - Create application record
- `PUT/PATCH /api/applications/{id}/` - Update record
- `DELETE /api/applications/{id}/` - Delete record
- `POST /api/applications/import/` - Import CSV / Excel file
- `GET /api/applications/export/` - Download Excel spreadsheet
- `GET /api/analytics/` - Analytics breakdown metrics

# 🤖 AI Career Assistant — Backend API

A production-ready **Django REST Framework** backend that uses **Google Gemini / OpenAI** to power an intelligent career assistant. It analyzes skill gaps, generates personalized learning roadmaps, and conducts AI-powered mock interviews.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Skill Gap Analysis** | AI compares your skills vs job requirements and generates a learning roadmap |
| 🎤 **Mock Interview Prep** | AI generates 5 tailored interview questions and evaluates your answers with scores |
| 👤 **User Management** | Create and manage user profiles with skills |
| 💼 **Job Management** | Post and list job descriptions with required skills |
| 🛡️ **Django Admin** | Visual browser-based database management panel |
| 🔄 **LLM Fallback** | Automatically falls back to mock data if API keys are missing |

---

## 🛠️ Tech Stack

- **Backend Framework:** Django 5.1.4 + Django REST Framework 3.15.2
- **Database:** SQLite (local) / PostgreSQL (production/Railway)
- **AI/LLM:** Google Gemini 2.5 Flash (primary) + OpenAI GPT-4o-mini (fallback)
- **Static Files:** WhiteNoise 6.7.0
- **Production Server:** Gunicorn 22.0.0
- **Deployment:** Railway.app

---

## 📋 Prerequisites

Before starting, you need:

1. **Python 3.13+** — [Download](https://python.org/downloads)
2. **Git** — [Download](https://git-scm.com)
3. **A Google Gemini API key** (free) — [Get it here](https://aistudio.google.com/app/apikey)
4. *(Optional)* **An OpenAI API key** — [Get it here](https://platform.openai.com/api-keys)

---

## 🚀 Local Setup (Step by Step)

### Step 1 — Clone the repository

```bash
git clone https://github.com/<your-username>/AI-Career-Assistant.git
cd AI-Career-Assistant/MABD/ai-career-backend
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Create your `.env` file

Create a file named `.env` in the `ai-career-backend/` folder:

```env
# =============================================
# AI Career Assistant — Environment Variables
# =============================================

# Database (leave as SQLite for local dev)
DATABASE_URL=sqlite:///db.sqlite3

# LLM Provider: "gemini" (recommended) or "openai"
LLM_PROVIDER=gemini

# Google Gemini API Key — get free at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here

# OpenAI API Key — optional fallback
OPENAI_API_KEY=your_openai_api_key_here

# Django (change this in production!)
SECRET_KEY=django-insecure-change-this-in-production
DEBUG=True
```

> ⚠️ **IMPORTANT:** Never commit your `.env` file to GitHub. It is already in `.gitignore`.

### Step 4 — Run database migrations

```bash
python manage.py makemigrations core
python manage.py migrate
```

### Step 5 — Create admin superuser

```bash
python manage.py createsuperuser
```

Or use the auto-create command:

```bash
python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'career_assistant.settings')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'Admin@1234')
    print('Superuser created: admin / Admin@1234')
else:
    print('Superuser already exists')
"
```

### Step 6 — Start the server

```bash
python manage.py runserver 8000
```

The server is now running at: **http://127.0.0.1:8000**

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8000/ | Home (health check) |
| http://127.0.0.1:8000/admin/ | Django Admin Panel |
| http://127.0.0.1:8000/api/jobs/ | Jobs API |
| http://127.0.0.1:8000/api/users/ | Users API |

---

## 📡 API Reference

### Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/users/` | Create a new user |
| `POST` | `/api/users/{id}/skills/` | Add a skill to user |
| `GET` | `/api/users/{id}/skills/` | Get user's skills |

**Create User — Request Body:**
```json
{
  "email": "ali@example.com",
  "first_name": "Ali",
  "last_name": "Khan"
}
```

**Add Skill — Request Body:**
```json
{
  "skill_name": "Python",
  "proficiency_level": "Expert",
  "years_experience": 3.0
}
```

---

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/jobs/` | Create a job posting |
| `GET` | `/api/jobs/` | List all jobs |

**Create Job — Request Body:**
```json
{
  "title": "Senior Backend Engineer",
  "company_name": "TechCorp",
  "description": "We need a Django expert with Docker and CI/CD experience.",
  "required_skills": ["Python", "Django", "Docker", "Kubernetes"],
  "location": "Remote",
  "salary_min": 80000,
  "salary_max": 120000
}
```

---

### Skill Gap Analysis (AI-Powered)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analysis/run/` | Run AI skill gap analysis |
| `GET` | `/api/analysis/history/{user_id}/` | Get user's analysis history |
| `GET` | `/api/analysis/{id}/report/` | Get a specific analysis report |

**Run Analysis — Request Body:**
```json
{
  "user_id": 1,
  "job_id": 1
}
```

**Response includes:**
- `missing_skills` — List of skills you need to learn (with priority)
- `proficiency_gap` — Skills you have but need to improve
- `learning_roadmap` — Phased learning plan with resources and duration
- `salary_projection` — Estimated % salary increase after acquiring skills

---

### Interview Preparation (AI-Powered)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/interview/start/` | Start a new interview session (AI generates 5 questions) |
| `GET` | `/api/interview/{id}/` | Get session status and questions |
| `POST` | `/api/interview/{id}/` | Submit an answer to a question |
| `POST` | `/api/interview/{id}/evaluate/` | Evaluate all answers with AI (get score + feedback) |

**Start Interview — Request Body:**
```json
{
  "user_id": 1,
  "job_id": 1
}
```

**Submit Answer — Request Body:**
```json
{
  "question_index": 0,
  "answer": "I design APIs using DRF ViewSets with proper serializers and caching layers..."
}
```

**Evaluation Response includes:**
- `score` — Overall score (0-100)
- `feedback.questions_feedback` — Per-question: score, strengths, weaknesses, suggestions
- `feedback.overall_feedback` — Full summary of candidate performance

---

## 🧪 Automated Tests

Run the full end-to-end test suite:

```bash
python -X utf8 test_django_flow.py
```

### Test Results (Latest Run)

```
=======================================================
  STEP 0 — Server Health Check
=======================================================
  [PASS] Server is reachable

=======================================================
  STEP 1 — User Management
=======================================================
  [PASS] Create user (201)
  [PASS] Duplicate email rejected (400)

=======================================================
  STEP 2 — Skills
=======================================================
  [PASS] Add skill 'Python' (201)
  [PASS] Add skill 'Django' (201)
  [PASS] Add skill 'React' (201)
  [PASS] List user skills (200)
  [PASS] 3 skills returned

=======================================================
  STEP 3 — Jobs
=======================================================
  [PASS] Create job (201)
  [PASS] List jobs (200)
  [PASS] At least 1 job exists

=======================================================
  STEP 4 — Skill Gap Analysis (AI)
=======================================================
  [PASS] Run skill gap analysis (200)
  [PASS] Analysis has missing_skills
  [PASS] Analysis has learning_roadmap
  [PASS] Analysis has salary_projection
  [PASS] Get analysis history (200)
  [PASS] History has entries
  [PASS] Get analysis report (200)

=======================================================
  STEP 5 — Interview Preparation (AI)
=======================================================
  [PASS] Start interview session (201)
  [PASS] Session has 5 questions
  [PASS] Status is 'started'
  [PASS] Submit answer 1 (200)
  [PASS] Submit answer 2 (200)
  [PASS] Submit answer 3 (200)
  [PASS] Submit answer 4 (200)
  [PASS] Submit answer 5 (200)
  [PASS] Get session detail (200)
  [PASS] Evaluate interview (200)
  [PASS] Status is 'evaluated'
  [PASS] Score is present
  [PASS] Feedback is present

=======================================================
  TEST SUMMARY
=======================================================
  Total : 31
  [PASS] Passed: 31
  [FAIL] Failed: 0
```

---

## 🌐 Deploy to Railway (Free)

Railway is the recommended platform. It supports Django natively, provides a free PostgreSQL database, and has no timeout limits.

### Do you need a Railway API key?
> ❌ **No!** Railway does NOT require any API key. You just **sign up with GitHub** for free. You get **$5 free credit/month** which is enough for this project.

### Step 1 — Push your code to GitHub
```bash
git add .
git commit -m "feat: production ready Django backend"
git push origin main
```

### Step 2 — Create Railway project
1. Go to **[railway.app](https://railway.app)** → Sign up with GitHub (free)
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repo → Branch: `main` (or `MABD`)
4. Set **Root Directory**: `MABD/ai-career-backend`

### Step 3 — Add Free PostgreSQL Database
1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway automatically sets `DATABASE_URL` — you don't need to do anything

### Step 4 — Set Environment Variables
In Railway → your web service → **"Variables"** tab, add:

| Variable | Value | Required? |
|----------|-------|-----------|
| `SECRET_KEY` | Any 50+ char random string | ✅ Yes |
| `DEBUG` | `False` | ✅ Yes |
| `GEMINI_API_KEY` | Your Gemini API key | ✅ Yes (for AI features) |
| `OPENAI_API_KEY` | Your OpenAI API key | ⚪ Optional |
| `LLM_PROVIDER` | `gemini` | ✅ Yes |

> `DATABASE_URL` is set automatically by Railway. Do NOT add it manually.

### Step 5 — Deploy!
Railway auto-deploys. It will:
1. Install dependencies from `requirements.txt`
2. Run `python manage.py migrate` automatically
3. Start `gunicorn` server

Your API will be live at: `https://your-app.up.railway.app`

### Step 6 — Create Admin Superuser on Railway
In Railway → your service → **"Settings"** → **"Railway Shell"**:
```bash
python manage.py createsuperuser
```

---

## 📁 Project Structure

```
ai-career-backend/
├── manage.py                    # Django entry point
├── requirements.txt             # All dependencies
├── Procfile                     # Railway: how to start the server
├── railway.json                 # Railway: build configuration
├── runtime.txt                  # Python 3.13
├── Dockerfile                   # Docker deployment
├── docker-compose.yml           # Local Docker + PostgreSQL
├── test_django_flow.py          # Automated API test suite
├── .env                         # Local secrets (NOT committed)
├── .gitignore                   # Files excluded from Git
│
├── career_assistant/            # Django project settings
│   ├── settings.py              # All configuration
│   ├── urls.py                  # Root URL routing
│   ├── wsgi.py / asgi.py        # Server entry points
│
└── core/                        # Main application
    ├── models.py                # Database models
    ├── serializers.py           # API data validation
    ├── views.py                 # API endpoint logic
    ├── urls.py                  # API URL routing
    ├── services.py              # AI/LLM business logic
    ├── admin.py                 # Django Admin config
    └── migrations/              # Database migration files
```

---

## 🔑 API Keys Guide

### Google Gemini API Key (Free — Recommended)
1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **"Create API Key"**
3. Copy the key and paste it in `.env` as `GEMINI_API_KEY`
4. Free tier: **1500 requests/day** — plenty for development

### OpenAI API Key (Optional Fallback)
1. Go to [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Click **"Create new secret key"**
3. Copy and paste in `.env` as `OPENAI_API_KEY`
4. Note: OpenAI requires credit card for paid usage

### What if I have no API keys?
> The app **still works!** It uses intelligent mock data as fallback. All endpoints return realistic AI-like responses so you can test without any API key.

---

## 🛡️ Django Admin Panel

Access the visual database management panel at:

**URL:** `http://127.0.0.1:8000/admin/` (local) or `https://your-app.railway.app/admin/` (production)

**Default credentials (local):**
```
Username: admin
Password: Admin@1234
```

In admin you can:
- View all users and their skills
- Browse all job postings
- See AI-generated skill gap analysis reports
- View interview sessions and evaluation results

---

## ❓ Troubleshooting

**Server won't start?**
```bash
pip install -r requirements.txt
python manage.py migrate
```

**"ModuleNotFoundError: No module named 'whitenoise'"?**
```bash
pip install whitenoise==6.7.0
```

**AI returning mock data instead of real responses?**
- Check your `GEMINI_API_KEY` in `.env`
- Make sure there are no extra spaces around the key

**Railway deploy fails?**
- Check logs in Railway → Deployments → latest deployment
- Make sure `Root Directory` is set to `MABD/ai-career-backend`

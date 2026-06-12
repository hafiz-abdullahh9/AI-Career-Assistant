# AI-Based Career Assistant System (Backend API)

Welcome to the backend repository of the **AI-Based Career Assistant System**. This backend is built using **FastAPI** and **SQLModel** to automate job searching, calculate skill gaps, conduct AI mock interviews, and optimize resumes/cover letters.

---

## 🚀 Key Features Implemented

*   **Skill Gap Analysis:** Computes gaps between user skill sets and target job postings, generating custom learning roadmaps and course suggestions via Google Gemini.
*   **Mock Interview Simulator:** Generates contextual interview questions (technical, behavioral, HR) based on a job description, saves transcripts, and yields grades and suggestions.
*   **Flexible Database Support:** Pre-configured database using SQLModel supporting **SQLite** (local development) and **PostgreSQL** (production cloud databases).
*   **Dual LLM Integration:** Ready-to-use services supporting **Google Gemini API** (using the new `google-genai` SDK and `gemini-2.5-flash` model) and **OpenAI API** (`gpt-4o-mini`).
*   **Docker Containerization:** Complete multi-stage `Dockerfile` and `docker-compose.yml` local orchestration for isolated execution.

---

## 🛠️ Tech Stack

*   **Core Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.13+)
*   **Database ORM:** [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic integration)
*   **Local Database:** SQLite (file-based)
*   **Production Database:** PostgreSQL (AWS RDS compatibility)
*   **AI Engine:** Google GenAI (`google-genai` SDK) & OpenAI SDK
*   **Runtime Containers:** Docker & Docker Compose

---

## 📁 Project Structure

```text
ai-career-backend/
├── database/
│   └── db.py              # SQLModel engine initialization and Session dependencies
├── models/
│   └── models.py          # Database table definitions and request/response schemas
├── routes/
│   ├── interview.py       # API routes for conducting and evaluating mock interviews
│   └── skill_gap.py       # API routes for managing users, skills, and skill gaps
├── services/
│   ├── config.py          # Configuration and dotenv settings
│   ├── llm.py             # LLM API orchestrator wrapper (Gemini & OpenAI)
│   ├── interview_service.py # Stateful business logic for mock interviews
│   └── skill_service.py   # Analysis engine logic for skill matching
├── main.py                # Application entrypoint and database lifespan hook
├── .env                   # Configuration file (environment variables & API keys)
├── requirements.txt       # Project python dependencies
├── Dockerfile             # Multi-stage production container build script
└── docker-compose.yml     # Multi-container local execution specification
```

---

## 💻 Local Setup & Execution Guide

### 1. Prerequisite Checklist
*   Python 3.13 installed.
*   Virtual environment tool installed.

### 2. Install Dependencies
Run these commands in your shell within the `ai-career-backend` folder:
```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows (CMD/Powershell):
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install all packages
pip install -r requirements.txt
```

### 3. Configure API Keys & Env Variables
Create a file named `.env` in the root folder (or edit the existing `.env`) and add your details:
```ini
DATABASE_URL=sqlite:///./career_assistant.db
LLM_PROVIDER=gemini # Toggle between 'gemini' and 'openai'
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

### 4. Run the API Server
Start the development server with hot-reloading enabled:
```bash
python -m uvicorn main:app --reload
```
Once started, open your browser and navigate to:
*   **API Docs (Swagger UI):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
*   **API Specs (Redoc):** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🐳 Running with Docker

You can run the entire backend stack (along with a dedicated PostgreSQL database container) using Docker Compose:

```bash
# Build and start services
docker-compose up --build

# Run in background (Detached)
docker-compose up -d

# Stop services
docker-compose down
```
The FastAPI documentation will be exposed at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## ☁️ AWS Cloud Production Deployment

For full instructions on how to deploy this containerized application to **AWS App Runner** and connect to **Amazon RDS (PostgreSQL)**, please check out our detailed guide:
👉 [aws_deployment_guide.md](aws_deployment_guide.md)

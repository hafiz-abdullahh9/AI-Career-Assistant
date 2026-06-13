# -*- coding: utf-8 -*-
import os, sys
os.environ["PYTHONIOENCODING"] = "utf-8"
"""
=============================================================
  AI Career Assistant - Django API Automated Test Suite
=============================================================
Tests all endpoints end-to-end using only stdlib + requests.
Run: python test_django_flow.py
"""

import sys
import json
import time
import requests

BASE_URL = "http://127.0.0.1:8000/api"

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"

results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    tag = "PASS" if condition else "FAIL"
    detail_str = f" | {detail}" if detail else ""
    print(f"  {status} {label}{detail_str}")
    results.append((tag, label))
    return condition

def section(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")

# ------------------------------------------------------------------
# STEP 0 — Health check
# ------------------------------------------------------------------
section("STEP 0 — Server Health Check")
try:
    r = requests.get(f"{BASE_URL}/jobs/", timeout=5)
    check("Server is reachable", r.status_code in (200, 404, 405))
except Exception as e:
    check("Server is reachable", False, str(e))
    print("\n  [!] Server is not running. Start it with: python manage.py runserver")
    sys.exit(1)

# ------------------------------------------------------------------
# STEP 1 — Create a User
# ------------------------------------------------------------------
section("STEP 1 — User Management")
r = requests.post(f"{BASE_URL}/users/", json={
    "email": f"test_{int(time.time())}@example.com",
    "first_name": "Ali",
    "last_name": "Khan"
})
check("Create user (201)", r.status_code == 201, r.text[:120])
user_id = r.json().get("id") if r.status_code == 201 else None

# Duplicate email should fail
if user_id:
    email_used = r.json()["email"]
    r2 = requests.post(f"{BASE_URL}/users/", json={
        "email": email_used,
        "first_name": "Duplicate",
        "last_name": "User"
    })
    check("Duplicate email rejected (400)", r2.status_code == 400)

# ------------------------------------------------------------------
# STEP 2 — Add Skills
# ------------------------------------------------------------------
section("STEP 2 — Skills")
if user_id:
    skills_to_add = [
        {"skill_name": "Python", "proficiency_level": "Expert", "years_experience": 3.0},
        {"skill_name": "Django", "proficiency_level": "Intermediate", "years_experience": 1.5},
        {"skill_name": "React", "proficiency_level": "Beginner", "years_experience": 0.5},
    ]
    for sk in skills_to_add:
        r = requests.post(f"{BASE_URL}/users/{user_id}/skills/", json=sk)
        check(f"Add skill '{sk['skill_name']}' (201)", r.status_code == 201)

    r = requests.get(f"{BASE_URL}/users/{user_id}/skills/")
    check("List user skills (200)", r.status_code == 200)
    check("3 skills returned", len(r.json()) == 3, f"got {len(r.json())}")
else:
    print("  [SKIP] No user_id available")

# ------------------------------------------------------------------
# STEP 3 — Create a Job
# ------------------------------------------------------------------
section("STEP 3 — Jobs")
r = requests.post(f"{BASE_URL}/jobs/", json={
    "title": "Senior Backend Engineer",
    "company_name": "TechCorp",
    "description": "We need a senior backend engineer with deep Python, Django, Docker, and Kubernetes experience. You will design scalable REST APIs and manage CI/CD pipelines.",
    "required_skills": ["Python", "Django", "Docker", "Kubernetes", "CI/CD"],
    "location": "Remote",
    "salary_min": 80000,
    "salary_max": 120000
})
check("Create job (201)", r.status_code == 201, r.text[:120])
job_id = r.json().get("id") if r.status_code == 201 else None

r = requests.get(f"{BASE_URL}/jobs/")
check("List jobs (200)", r.status_code == 200)
check("At least 1 job exists", len(r.json()) >= 1)

# ------------------------------------------------------------------
# STEP 4 — Skill Gap Analysis
# ------------------------------------------------------------------
section("STEP 4 — Skill Gap Analysis")
analysis_id = None
if user_id and job_id:
    r = requests.post(f"{BASE_URL}/analysis/run/", json={
        "user_id": user_id,
        "job_id": job_id
    })
    check("Run skill gap analysis (200)", r.status_code == 200, r.text[:150])
    if r.status_code == 200:
        data = r.json()
        analysis_id = data.get("id")
        check("Analysis has missing_skills", bool(data.get("missing_skills")))
        check("Analysis has learning_roadmap", bool(data.get("learning_roadmap")))
        check("Analysis has salary_projection", data.get("salary_projection") is not None)

    # History
    r = requests.get(f"{BASE_URL}/analysis/history/{user_id}/")
    check("Get analysis history (200)", r.status_code == 200)
    check("History has entries", len(r.json()) >= 1)

    # Single report
    if analysis_id:
        r = requests.get(f"{BASE_URL}/analysis/{analysis_id}/report/")
        check("Get analysis report (200)", r.status_code == 200)
else:
    print("  [SKIP] user_id or job_id missing")

# ------------------------------------------------------------------
# STEP 5 — Interview Prep
# ------------------------------------------------------------------
section("STEP 5 — Interview Preparation")
session_id = None
if user_id and job_id:
    r = requests.post(f"{BASE_URL}/interview/start/", json={
        "user_id": user_id,
        "job_id": job_id
    })
    check("Start interview session (201)", r.status_code == 201, r.text[:150])
    if r.status_code == 201:
        data = r.json()
        session_id = data.get("id")
        questions = data.get("question_set", [])
        check("Session has 5 questions", len(questions) == 5, f"got {len(questions)}")
        check("Status is 'started'", data.get("status") == "started")

    # Submit answers
    if session_id:
        answers = [
            "I use Django REST Framework with proper serializers, viewsets, and caching layers.",
            "I use multi-stage Docker builds to minimize image size and improve security.",
            "I analyze slow queries using EXPLAIN ANALYZE and add proper indexes.",
            "I once learned Kubernetes in a week to deploy a critical service. I used the official docs and hands-on practice.",
            "Redis dramatically improves performance by caching frequently accessed data and reducing DB load."
        ]
        for i, ans in enumerate(answers):
            r = requests.post(f"{BASE_URL}/interview/{session_id}/", json={
                "question_index": i,
                "answer": ans
            })
            check(f"Submit answer {i+1} (200)", r.status_code == 200)

        # Get session state
        r = requests.get(f"{BASE_URL}/interview/{session_id}/")
        check("Get session detail (200)", r.status_code == 200)

        # Evaluate
        r = requests.post(f"{BASE_URL}/interview/{session_id}/evaluate/")
        check("Evaluate interview (200)", r.status_code == 200, r.text[:150])
        if r.status_code == 200:
            data = r.json()
            check("Status is 'evaluated'", data.get("status") == "evaluated")
            check("Score is present", data.get("score") is not None)
            check("Feedback is present", bool(data.get("feedback")))
else:
    print("  [SKIP] user_id or job_id missing")

# ------------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------------
section("TEST SUMMARY")
passed = sum(1 for tag, _ in results if tag == "PASS")
failed = sum(1 for tag, _ in results if tag == "FAIL")
total = len(results)
print(f"\n  Total : {total}")
print(f"  {PASS} Passed: {passed}")
print(f"  {FAIL} Failed: {failed}")

if failed > 0:
    print("\n  Failed tests:")
    for tag, label in results:
        if tag == "FAIL":
            print(f"    - {label}")

print()
sys.exit(0 if failed == 0 else 1)

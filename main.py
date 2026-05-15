import shutil
import os
import json
import hashlib
import logging
import httpx
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import unquote

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from parser import parse_resume
from query_generator import generate_job_queries
from scrapper import scrape_google_jobs
from database import engine, SessionLocal
from models import Base, UserProfile, Job, User, Application
from auth import validate_name, validate_gmail, generate_verify_token, send_verification_email

# --- Config ---
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY")

N8N_NEW_PROFILE_WEBHOOK = "http://localhost:5678/webhook/new-profile"
N8N_APPLY_JOB_WEBHOOK = "http://localhost:5678/webhook/apply-job"

# --- Logging ---
logger = logging.getLogger("acris")
logging.basicConfig(level=logging.INFO)

# --- Database ---
def get_db():
    """Dependency for FastAPI to inject DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Background Jobs ---
def auto_fetch_jobs_task():
    """Background task: Fetch jobs for all users every 6 hours."""
    logger.info("Auto-fetch jobs task started...")
    db = SessionLocal()
    try:
        users = db.query(UserProfile).all()
        if not users:
            logger.info("No user profiles found")
            return
        
        for user in users:
            try:
                job_role = user.job_role or ""
                location = user.location or ""
                skills = json.loads(user.filtered_skills or "[]")
                
                queries = generate_job_queries(job_role, skills, location)
                all_jobs = []
                
                for q in queries:
                    jobs = scrape_google_jobs(q, location)
                    all_jobs.extend(jobs)
                
                # Deduplicate by link
                seen_links = set()
                unique_jobs = []
                for job in all_jobs:
                    if job["link"] not in seen_links:
                        seen_links.add(job["link"])
                        unique_jobs.append(job)
                
                # Clear old jobs, add new ones
                db.query(Job).filter(Job.user_email == user.email).delete()
                for job in unique_jobs[:10]:
                    db.add(Job(
                        title=job["title"],
                        company=job["company"],
                        location=job["location"],
                        link=job["link"],
                        user_email=user.email
                    ))
                db.commit()
                logger.info(f"Updated {len(unique_jobs[:10])} jobs for {user.email}")
            except Exception as e:
                logger.error(f"Failed for {user.email}: {e}")
                db.rollback()
    except Exception as e:
        logger.error(f"Auto-fetch failed: {e}")
    finally:
        db.close()

# --- Scheduler ---
scheduler = BackgroundScheduler()

def start_n8n():
    """Start n8n automatically when FastAPI starts."""
    import subprocess
    import socket

    # Check if n8n already running on port 5678
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', 5678))
        sock.close()
        if result == 0:
            logger.info("n8n already running on port 5678 — skipping start")
            return
    except Exception:
        pass

    # Start n8n as background process
    try:
        subprocess.Popen(
            ["n8n", "start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
        )
        logger.info("n8n started automatically on http://localhost:5678")
    except Exception as e:
        logger.error(f"Failed to start n8n: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_n8n()

    scheduler.add_job(
        auto_fetch_jobs_task,
        trigger=IntervalTrigger(hours=6),
        id="auto_fetch_jobs",
        name="Auto-fetch jobs every 6 hours",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Background scheduler started (auto-fetch every 6 hours)")
    yield
    scheduler.shutdown(wait=False)
    logger.info("✅ Background scheduler stopped")

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)
Base.metadata.create_all(bind=engine)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(BASE_DIR / "uploads")), name="uploads")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# --- Utilities ---
def get_current_user(request: Request):
    """Dependency: Get current user from session."""
    if "user" not in request.session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.session["user"]

def calculate_match_score(job_title: str, job_role: str, user_skills: set) -> int:
    """Calculate match score between job and user profile."""
    title_lower = job_title.lower()
    role_lower = job_role.lower()
    role_words = [w for w in role_lower.split() if len(w) > 2]
    role_hits = sum(1 for w in role_words if w in title_lower)
    
    if role_hits >= 4:
        role_score = 75
    elif role_hits >= len(role_words) and len(role_words) > 0:
        role_score = 40
    else:
        role_score = int(40 * role_hits / max(len(role_words), 1))
    
    if user_skills:
        skill_hits = sum(1 for skill in user_skills if skill.lower() in title_lower)
        skill_ratio = min(skill_hits / max(len(user_skills), 1), 1.0)
        skill_score = 20 + int(40 * skill_ratio) if skill_hits > 0 else 0
    else:
        skill_score = 30
    
    return min(100, role_score + skill_score)

# --- Public Pages ---

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html", {})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})

# --- Authentication ---

@app.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    name:     str = Form(...),
    email:    str = Form(...),
    password: str = Form(...)
):
    name_ok, name_err = validate_name(name)
    if not name_ok:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": name_err},
            status_code=400
        )

    email_ok, email_err = validate_gmail(email)
    if not email_ok:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": email_err},
            status_code=400
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Password must be at least 8 characters."},
            status_code=400
        )

    db = SessionLocal()
    existing = db.query(User).filter(User.email == email.strip().lower()).first()
    if existing:
        db.close()
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "An account with this Gmail already exists."},
            status_code=400
        )

    token, expiry      = generate_verify_token()
    password_hash      = hashlib.sha256(password.encode()).hexdigest()

    new_user = User(
        name               = name.strip(),
        email              = email.strip().lower(),
        password_hash      = password_hash,
        is_verified        = False,
        verify_token       = token,
        verify_token_expiry= expiry,
    )
    db.add(new_user)
    db.commit()
    db.close()

    sent = send_verification_email(
        to_email = email.strip().lower(),
        name     = name.strip(),
        token    = token,
    )

    if not sent:
        logger.warning(f"Verification email NOT sent for {email} — check SMTP config.")

    return RedirectResponse(
        f"/verify-pending?email={email.strip().lower()}",
        status_code=303
    )

@app.get("/verify-pending", response_class=HTMLResponse)
async def verify_pending(request: Request, email: str = ""):
    return templates.TemplateResponse(
        request, "verify.html",
        {"email": email}
    )

# ---------------- VERIFY EMAIL (link from email) ---------------- #
@app.get("/verify-email", response_class=HTMLResponse)
async def verify_email(request: Request, token: str = ""):
    if not token:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Invalid or missing verification link."},
            status_code=400
        )

    db   = SessionLocal()
    user = db.query(User).filter(User.verify_token == token).first()

    if not user:
        db.close()
        return templates.TemplateResponse(
            request, "verify_result.html",
            {
                "success": False,
                "message": "This verification link is invalid or has already been used."
            }
        )

    if user.verify_token_expiry and datetime.now() > user.verify_token_expiry:
        db.close()
        return templates.TemplateResponse(
            request, "verify_result.html",
            {
                "success": False,
                "message": "This verification link has expired. Please register again."
            }
        )

    if user.is_verified:
        db.close()
        return RedirectResponse("/login", status_code=303)

    user.is_verified         = True
    user.verify_token        = None
    user.verify_token_expiry = None
    db.commit()

    # Save before closing session (avoids DetachedInstanceError)
    verified_email = user.email
    verified_name  = user.name
    db.close()

    logger.info(f"Email verified: {verified_email}")

    return templates.TemplateResponse(
        request, "verify_result.html",
        {
            "success": True,
            "message": f"Your email has been verified. Welcome, {verified_name.split()[0]}!",
            "name":    verified_name,
        }
    )

@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    db = next(get_db())
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user = db.query(User).filter(
        User.email == email,
        User.password_hash == password_hash
    ).first()
    
    if not user:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid credentials"},
            status_code=400
        )
    
    if not user.is_verified:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Please verify your email before logging in. "
                      "Check your inbox for the verification link."},
            status_code=403
        )
    
    request.session["user"] = {"name": user.name, "email": user.email}
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/auth/google")
async def auth_google(request: Request):
    redirect_uri = request.url_for('auth_google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    request.session["user"] = {
        "name": user["name"],
        "email": user["email"]
    }
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

# --- Dashboard & Profile ---

@app.get("/dashboard", response_class=HTMLResponse)
async def home(
    request: Request,
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_data = db.query(UserProfile)\
        .filter(UserProfile.email == user["email"])\
        .order_by(UserProfile.id.desc())\
        .first()
    
    jobs = db.query(Job).filter(Job.user_email == user["email"]).all()
    applications = db.query(Application)\
        .filter(Application.user_email == user["email"])\
        .order_by(Application.applied_at.desc())\
        .all()
    
    if user_data:
        user_data.filtered_skills = json.loads(user_data.filtered_skills or "[]")
        if jobs:
            user_skills = set(user_data.filtered_skills)
            for job in jobs:
                job.match_score = calculate_match_score(
                    job.title,
                    user_data.job_role,
                    user_skills
                )
            jobs = sorted(jobs, key=lambda j: j.match_score, reverse=True)
    
    show_data = request.session.get("show_data", False)
    request.session["show_data"] = False
    
    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "user": user,
            "prefs": user_data if show_data else None,
            "jobs": jobs if show_data else [],
            "applications": applications
        }
    )

@app.post("/submit-profile")
async def submit_profile(
    request: Request,
    job_role: str = Form(...),
    experience: str = Form(...),
    expected_salary: str = Form(...),
    location: str = Form(...),
    job_type: str = Form(...),
    work_mode: str = Form(...),
    resume: UploadFile = File(None),
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    resume_path = None
    all_skills = []
    filtered_skills = []
    
    if resume and resume.filename:
        dest = UPLOAD_DIR / resume.filename.replace(" ", "_")
        with dest.open("wb") as f:
            shutil.copyfileobj(resume.file, f)
        resume_path = str(dest)
        parsed = parse_resume(resume_path, job_role)
        all_skills = parsed.get("all_skills", [])
        filtered_skills = parsed.get("filtered_skills", [])
    
    if not filtered_skills:
        filtered_skills = all_skills[:3]
    
    jobs = scrape_google_jobs(job_role, location)
    
    db.query(Job).filter(Job.user_email == user["email"]).delete()
    db.query(UserProfile).filter(UserProfile.email == user["email"]).delete()
    
    db_user = UserProfile(
        name=user["name"],
        email=user["email"],
        job_role=job_role,
        experience_input=experience,
        expected_salary=expected_salary,
        location=location,
        job_type=job_type,
        work_mode=work_mode,
        resume_path=resume_path,
        all_skills=json.dumps(all_skills),
        filtered_skills=json.dumps(filtered_skills),
    )
    db.add(db_user)
    
    # Save jobs
    for job in jobs:
        db.add(Job(
            title=job["title"],
            company=job["company"],
            location=job["location"],
            link=job["link"],
            user_email=user["email"]
        ))
    
    db.commit()
    request.session["show_data"] = True
    
    # Trigger n8n webhook
    try:
        jobs_payload = [
            {
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "link": j["link"]
            }
            for j in jobs
        ]
        httpx.post(
            N8N_NEW_PROFILE_WEBHOOK,
            json={
                "email": user["email"],
                "name": user["name"],
                "jobs": jobs_payload
            },
            timeout=5.0
        )
        logger.info(f"✅ n8n webhook triggered for {user['email']}")
    except Exception as e:
        logger.error(f"n8n webhook failed: {e}")
    
    return RedirectResponse("/dashboard", status_code=303)

# --- Applications & Job Tracking ---

@app.get("/track-apply")
async def track_apply(
    request: Request,
    email: str,
    job_title: str,
    company: str,
    job_link: str,
    db: Session = Depends(get_db)
):
    job_title = unquote(job_title)
    company = unquote(company)
    job_link = unquote(job_link)
    
    existing = db.query(Application).filter(
        Application.user_email == email,
        Application.job_title == job_title,
        Application.company == company
    ).first()
    
    if not existing:
        application = Application(
            user_email=email,
            user_name=email.split("@")[0],
            job_title=job_title,
            company=company,
            job_link=job_link,
            status="pending"
        )
        db.add(application)
        db.commit()
        logger.info(f"Job tracked: {email} → {job_title}")
    
    return RedirectResponse(job_link, status_code=302)

@app.post("/apply-job")
async def apply_job(
    request: Request,
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    data = await request.json()
    job_title = data.get("job_title")
    company = data.get("company")
    job_link = data.get("job_link")
    
    existing = db.query(Application).filter(
        Application.user_email == user["email"],
        Application.job_title == job_title,
        Application.company == company
    ).first()
    
    if existing:
        return JSONResponse({"status": "already_applied"})
    
    application = Application(
        user_email=user["email"],
        user_name=user["name"],
        job_title=job_title,
        company=company,
        job_link=job_link,
        status="pending"
    )
    db.add(application)
    db.commit()
    app_id = application.id
    
    try:
        httpx.post(
            N8N_APPLY_JOB_WEBHOOK,
            json={
                "email": user["email"],
                "name": user["name"],
                "job_title": job_title,
                "company": company,
                "job_link": job_link,
                "app_id": app_id
            },
            timeout=5.0
        )
    except Exception as e:
        logger.error(f"n8n webhook failed: {e}")
    
    return JSONResponse({"status": "success"})

@app.post("/mark-applied")
async def mark_applied(
    request: Request,
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    data = await request.json()
    app_id = data.get("app_id")
    
    application = db.query(Application).filter(
        Application.id == app_id,
        Application.user_email == user["email"]
    ).first()
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    application.status = "applied"
    application.updated_at = datetime.now()
    db.commit()
    
    return JSONResponse({"status": "success"})

@app.post("/update-application-status")
async def update_application_status(
    request: Request,
    db: Session = Depends(get_db)
):
    data = await request.json()
    
    application = db.query(Application).filter(
        Application.user_email == data.get("email"),
        Application.job_title == data.get("job_title")
    ).first()
    
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    application.status = data.get("status")
    application.notes = data.get("notes", "")
    application.updated_at = datetime.now()
    db.commit()
    
    return JSONResponse({"status": "success"})

@app.get("/my-applications")
async def my_applications(
    request: Request,
    user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    applications = db.query(Application)\
        .filter(Application.user_email == user["email"])\
        .order_by(Application.applied_at.desc())\
        .all()
    
    return JSONResponse({
        "status": "success",
        "applications": [
            {
                "id": a.id,
                "job_title": a.job_title,
                "company": a.company,
                "job_link": a.job_link,
                "status": a.status,
                "notes": a.notes,
                "applied_at": str(a.applied_at)
            }
            for a in applications
        ]
    })

@app.get("/auto-fetch-jobs")
async def auto_fetch_jobs_endpoint(db: Session = Depends(get_db)):
    auto_fetch_jobs_task()
    return {"status": "jobs updated"}

# --- Server Startup ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
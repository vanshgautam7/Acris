# ACRIS — AI Career Intelligence System

An AI-powered job search platform that parses your resume, extracts skills, and matches you with relevant job listings.

---

## Project Structure

```
acris/
├── static/
│   └── style.css           # All styles
├── templates/
│   ├── landing.html        # Home / landing page
│   ├── login.html          # Sign in page
│   ├── register.html       # Create account page
│   ├── dashboard.html      # Main dashboard
│   ├── verify.html         # Check your inbox page
│   └── verify_result.html  # Verification success/fail page
├── uploads/                # Uploaded resumes (auto-created)
├── main.py                 # FastAPI app & routes
├── auth.py                 # Auth, validation, and email logic
├── models.py               # SQLAlchemy DB models
├── database.py             # DB engine & session setup
├── parser.py               # Resume PDF parser + skill extractor
├── scrapper.py             # SerpAPI Google Jobs scraper
├── query_generator.py      # Job search query builder
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
└── README.md
```

---

## Setup

### 1. Clone / download the project

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Download spaCy language model
```bash
python -m spacy download en_core_web_sm
```

### 5. Set up environment variables
```bash
cp .env.example .env
# Edit .env and fill in your Google OAuth credentials, SECRET_KEY, and Gmail SMTP details
```

### 6. Add required JSON files
Place these in the project root:
- `skills.json` — flat or nested list of all known skills
- `job_skills.json` — mapping of job roles to required skills

### 7. Setup n8n (Optional)
If you want to use the automated background workflows, install n8n globally:
```bash
npm install -g n8n
```
It will automatically start in the background when you run the FastAPI app.

### 8. Run the app
```bash
uvicorn main:app --reload
```

Open http://localhost:8000 in your browser.

---

## Environment Variables

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | From Google Cloud Console OAuth credentials |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console OAuth credentials |
| `SECRET_KEY` | Random string for session signing |
| `GMAIL_SENDER` | The Gmail address used to send verification emails |
| `GMAIL_APP_PASSWORD` | The 16-character Google App Password for that Gmail |
| `BASE_URL` | Base URL of your app (e.g. `http://localhost:8001`) |
| `SERPAPI_KEY` | API key for Google Jobs scraper |

---

## Key Dependencies

| Package | Purpose |
|---|---|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM / database |
| `authlib` | Google OAuth |
| `pdfplumber` | PDF text extraction |
| `spacy` | NLP skill extraction |
| `requests` | SerpAPI HTTP calls |

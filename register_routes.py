# ════════════════════════════════════════════════════════════
# PASTE THIS BLOCK AT THE TOP OF main.py  (with your other imports)
# ════════════════════════════════════════════════════════════

from auth import (
    validate_name,
    validate_gmail,
    generate_verify_token,
    send_verification_email,
)


# ════════════════════════════════════════════════════════════
# REPLACE your existing GET /register, POST /register, and
# add the two new routes below (GET /verify-email and
# GET /verify-pending) in place of the old register block.
# ════════════════════════════════════════════════════════════


# ---------------- REGISTER PAGE ---------------- #
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})


# ---------------- REGISTER (EMAIL/PASSWORD) ---------------- #
@app.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    name:     str = Form(...),
    email:    str = Form(...),
    password: str = Form(...)
):
    # ── 1. Name validation ──────────────────────────────────
    name_ok, name_err = validate_name(name)
    if not name_ok:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": name_err},
            status_code=400
        )

    # ── 2. Gmail validation ─────────────────────────────────
    email_ok, email_err = validate_gmail(email)
    if not email_ok:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": email_err},
            status_code=400
        )

    # ── 3. Password length ──────────────────────────────────
    if len(password) < 8:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "Password must be at least 8 characters."},
            status_code=400
        )

    # ── 4. Duplicate check ──────────────────────────────────
    db = SessionLocal()
    existing = db.query(User).filter(User.email == email.strip().lower()).first()
    if existing:
        db.close()
        return templates.TemplateResponse(
            request, "register.html",
            {"error": "An account with this Gmail already exists."},
            status_code=400
        )

    # ── 5. Create unverified user ───────────────────────────
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

    # ── 6. Send verification email ──────────────────────────
    sent = send_verification_email(
        to_email = email.strip().lower(),
        name     = name.strip(),
        token    = token,
    )

    if not sent:
        # Email failed — still created the account; show a warning
        logger.warning(f"Verification email NOT sent for {email} — check SMTP config.")

    # ── 7. Redirect to "check your inbox" page ──────────────
    return RedirectResponse(
        f"/verify-pending?email={email.strip().lower()}",
        status_code=303
    )


# ---------------- VERIFY PENDING (info page) ---------------- #
@app.get("/verify-pending", response_class=HTMLResponse)
async def verify_pending(request: Request, email: str = ""):
    return templates.TemplateResponse(
        request, "verify_pending.html",
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

    # ── Token not found ──
    if not user:
        db.close()
        return templates.TemplateResponse(
            request, "verify_result.html",
            {
                "success": False,
                "message": "This verification link is invalid or has already been used."
            }
        )

    # ── Token expired ──
    if user.verify_token_expiry and datetime.now() > user.verify_token_expiry:
        db.close()
        return templates.TemplateResponse(
            request, "verify_result.html",
            {
                "success": False,
                "message": "This verification link has expired. Please register again."
            }
        )

    # ── Already verified ──
    if user.is_verified:
        db.close()
        return RedirectResponse("/login", status_code=303)

    # ── Activate account ──
    user.is_verified         = True
    user.verify_token        = None    # invalidate the token
    user.verify_token_expiry = None
    db.commit()
    db.close()

    logger.info(f"Email verified: {user.email}")

    return templates.TemplateResponse(
        request, "verify_result.html",
        {
            "success": True,
            "message": f"Your email has been verified. Welcome, {user.name.split()[0]}!",
            "name":    user.name,
        }
    )


# ════════════════════════════════════════════════════════════
# ALSO UPDATE your POST /login route — add this check AFTER
# confirming password is correct (before setting session):
#
#   if not user.is_verified:
#       return templates.TemplateResponse(
#           request, "login.html",
#           {"error": "Please verify your email before logging in. "
#                     "Check your inbox for the verification link."},
#           status_code=403
#       )
#
# ════════════════════════════════════════════════════════════
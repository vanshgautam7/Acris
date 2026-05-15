"""
auth.py — ACRIS validation and email-verification helpers
==========================================================

Responsibilities
----------------
1. validate_name(name)         – blocks numbers, symbols, very short strings
2. validate_gmail(email)       – only @gmail.com + MX DNS check on the domain
3. generate_verify_token()     – cryptographically secure URL-safe token
4. send_verification_email()   – sends HTML email via Gmail SMTP (App Password)

Environment variables required (.env)
--------------------------------------
GMAIL_SENDER      = acris.jobs.portal@gmail.com
GMAIL_APP_PASSWORD=        ← 16-char Google App Password
BASE_URL          = http://localhost:8001      ← or your deployed domain
"""

import os
import re
import uuid
import smtplib
import logging
import dns.resolver

from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("acris.auth")


# ─────────────────────────────────────────────────────────────
# 1. NAME VALIDATION
# ─────────────────────────────────────────────────────────────

def validate_name(name: str) -> tuple[bool, str]:
    """
    Rules:
    - 2–60 characters
    - Only letters, spaces, hyphens, apostrophes  (no digits, no symbols)
    - Must contain at least two letters (blocks single-char entries)
    - No leading/trailing spaces (we strip before checking)

    Returns (True, "") on success, (False, error_message) on failure.
    """
    name = name.strip()

    if len(name) < 2:
        return False, "Name must be at least 2 characters."

    if len(name) > 60:
        return False, "Name must be under 60 characters."

    # Only letters, spaces, hyphens, apostrophes
    if not re.match(r"^[A-Za-z][A-Za-z\s'\-]+$", name):
        return False, "Name must contain only letters. Numbers and special characters are not allowed."

    # At least two letters (not just a hyphen or apostrophe)
    letter_count = sum(1 for c in name if c.isalpha())
    if letter_count < 2:
        return False, "Please enter your real name."

    return True, ""


# ─────────────────────────────────────────────────────────────
# 2. GMAIL VALIDATION
# ─────────────────────────────────────────────────────────────

# Compiled once at import time for speed
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9._+\-]{4,28}[a-zA-Z0-9]@gmail\.com$"
)
# Gmail local-part rules:
#   - 6–30 characters total (we check 6+ above with the anchors + {4,28})
#   - Only letters, digits, dots, underscores, hyphens, plus signs
#   - Cannot start or end with a dot (regex above covers start; dot-at-end
#     would require the last char to be alphanumeric — covered by [a-zA-Z0-9]$)
#   - We normalise to lowercase before matching

_ALLOWED_DOMAIN = "gmail.com"


def _mx_exists(domain: str) -> bool:
    """Return True if the domain has at least one MX record."""
    try:
        records = dns.resolver.resolve(domain, "MX", lifetime=3)
        return len(records) > 0
    except Exception:
        return False


def validate_gmail(email: str) -> tuple[bool, str]:
    """
    Validates that:
    1. The email ends with @gmail.com  (no other providers accepted)
    2. The local part matches Gmail's own character rules
    3. The gmail.com domain resolves an MX record (DNS sanity check)
       — this catches completely fabricated domains but gmail.com itself
         will always resolve, so it acts as a structural guard.

    Returns (True, "") on success, (False, error_message) on failure.
    """
    email = email.strip().lower()

    # ── Must be @gmail.com ──
    if not email.endswith("@gmail.com"):
        return False, "Only Gmail addresses (@gmail.com) are accepted."

    # ── Regex format check ──
    if not _EMAIL_RE.match(email):
        return (
            False,
            "Invalid Gmail address. "
            "Gmail usernames are 6–30 characters and can only contain "
            "letters, numbers, dots, underscores, or hyphens."
        )

    # ── Consecutive dots check (Gmail forbids them) ──
    local = email.split("@")[0]
    if ".." in local:
        return False, "Gmail addresses cannot contain consecutive dots."

    # ── MX record check ──
    if not _mx_exists(_ALLOWED_DOMAIN):
        # If DNS itself is down, don't block registration — log and continue
        logger.warning("MX lookup for gmail.com failed — skipping DNS check.")

    return True, ""


# ─────────────────────────────────────────────────────────────
# 3. TOKEN GENERATION
# ─────────────────────────────────────────────────────────────

def generate_verify_token() -> tuple[str, datetime]:
    """
    Returns (token_string, expiry_datetime).
    Token is a URL-safe UUID4 hex string.
    Expiry is 24 hours from now.
    """
    token  = uuid.uuid4().hex          # 32-char hex, URL-safe
    expiry = datetime.now() + timedelta(hours=24)
    return token, expiry


# ─────────────────────────────────────────────────────────────
# 4. SEND VERIFICATION EMAIL
# ─────────────────────────────────────────────────────────────

def send_verification_email(to_email: str, name: str, token: str) -> bool:
    """
    Sends an HTML verification email to `to_email`.
    Uses Gmail SMTP with an App Password (never your real Gmail password).

    Returns True on success, False on failure.
    """
    sender   = os.getenv("GMAIL_SENDER", "")
    password = os.getenv("GMAIL_APP_PASSWORD", "")
    base_url = os.getenv("BASE_URL", "http://localhost:8001")

    if not sender or not password:
        logger.error(
            "GMAIL_SENDER or GMAIL_APP_PASSWORD not set in .env — "
            "cannot send verification email."
        )
        return False

    verify_link = f"{base_url}/verify-email?token={token}"

    # ── Build MIME message ──
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your ACRIS account"
    msg["From"]    = f"ACRIS <{sender}>"
    msg["To"]      = to_email

    first_name = name.split()[0].capitalize()

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    </head>
    <body style="margin:0;padding:0;background:#0a0c0f;font-family:'DM Sans',Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td align="center" style="padding:40px 20px;">
            <table width="520" cellpadding="0" cellspacing="0"
                   style="background:#111418;border-radius:12px;
                          border:1px solid rgba(255,255,255,0.08);
                          overflow:hidden;">

              <!-- Header -->
              <tr>
                <td style="padding:32px 40px 24px;
                           border-bottom:1px solid rgba(255,255,255,0.08);">
                  <span style="font-size:1.4rem;color:#f0ede6;letter-spacing:0.04em;">
                    AC<span style="color:#c8f0a0;">R</span>IS
                  </span>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:36px 40px;">
                  <p style="color:#8a8a8a;font-size:0.8rem;
                             letter-spacing:0.1em;text-transform:uppercase;
                             margin:0 0 12px;">Account verification</p>

                  <h1 style="color:#f0ede6;font-size:1.5rem;
                              font-weight:400;margin:0 0 16px;line-height:1.3;">
                    Welcome, {first_name}.
                  </h1>

                  <p style="color:#8a8a8a;font-size:0.9rem;
                             line-height:1.7;margin:0 0 28px;">
                    Your ACRIS account has been created. Click the button below
                    to verify your email address and activate your account.
                    This link expires in <strong style="color:#f0ede6;">24 hours</strong>.
                  </p>

                  <a href="{verify_link}"
                     style="display:inline-block;background:#c8f0a0;color:#0a0c0f;
                            text-decoration:none;font-weight:500;font-size:0.9rem;
                            padding:12px 28px;border-radius:8px;
                            letter-spacing:0.02em;">
                    Verify my email
                  </a>

                  <p style="color:#8a8a8a;font-size:0.75rem;
                             margin:28px 0 0;line-height:1.6;">
                    If the button doesn't work, paste this link into your browser:<br/>
                    <a href="{verify_link}"
                       style="color:#c8f0a0;word-break:break-all;">
                      {verify_link}
                    </a>
                  </p>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="padding:20px 40px;
                           border-top:1px solid rgba(255,255,255,0.08);">
                  <p style="color:#555;font-size:0.72rem;margin:0;line-height:1.6;">
                    If you did not create an ACRIS account, you can safely ignore
                    this email. &mdash; LPU MCA Project &copy; 2026
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    plain_body = (
        f"Hi {first_name},\n\n"
        f"Please verify your ACRIS account by visiting:\n{verify_link}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"— ACRIS, LPU MCA Project"
    )

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body,  "html"))

    # ── Send via Gmail SMTP ──
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
        logger.info(f"Verification email sent → {to_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail SMTP authentication failed. "
            "Make sure GMAIL_APP_PASSWORD is a valid 16-char App Password, "
            "not your real Gmail password."
        )
        return False
    except Exception as e:
        logger.error(f"Failed to send verification email to {to_email}: {e}")
        return False
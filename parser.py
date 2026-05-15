import json
import re
import pdfplumber
from pathlib import Path
import spacy
import logging

logger = logging.getLogger("acris.parser")

nlp = spacy.load("en_core_web_sm")


skills_path = Path("skills.json")

with open(skills_path, "r") as f:
    raw_data = json.load(f)


def flatten_skills(data):
    skills = []

    if isinstance(data, dict):
        for value in data.values():
            skills.extend(flatten_skills(value))

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                skills.append(item.lower().strip())
            else:
                skills.extend(flatten_skills(item))

    return skills


SKILLS_DB = flatten_skills(raw_data)


def extract_text_from_pdf(pdf_path):
    text = ""

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if page_text:
                    text += page_text + " "
    except Exception as e:
        logger.error(f"PDF reading error: {e}")

    return text


def clean_text(text):
    text = text.lower()
    text = re.sub(r'([a-z])\s+([a-z])', r'\1\2', text)
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_skills(text):

    cleaned_text = clean_text(text)
    no_space_text = cleaned_text.replace(" ", "")
    words = set(cleaned_text.split())

    skills_found = []

    for skill in SKILLS_DB:

        skill_clean = clean_text(skill)
        parts = skill_clean.split()

        # Direct match
        if skill_clean in cleaned_text:
            skills_found.append(skill)
            continue

        # Joined match (e.g. machinelearning)
        joined = "".join(parts)
        if joined in no_space_text:
            skills_found.append(skill)
            continue

        # Word match
        if all(part in words for part in parts):
            skills_found.append(skill)

    return sorted(list(set(skills_found)))


def extract_experience(text):

    text = text.lower()

    matches = re.findall(r'(\d+)\+?\s+years?', text)

    if matches:
        return max(matches) + " years"

    return "Not found"


def select_relevant_skills(job_role, resume_skills):

    with open("job_skills.json") as f:
        job_skill_map = json.load(f)

    role = job_role.strip()

    if role not in job_skill_map:
        return resume_skills[:6]

    required_skills = job_skill_map[role]

    filtered = []

    for skill in resume_skills:
        if skill.lower() in required_skills:
            filtered.append(skill)

    if not filtered:
        filtered = resume_skills[:6]

    return filtered


def parse_resume(file_path, job_role=None):

    text = extract_text_from_pdf(file_path)

    extracted_skills = extract_skills(text)

    logger.debug("Extracted skills (all): %s", extracted_skills)

    filtered_skills = []

    if job_role:
        filtered_skills = select_relevant_skills(job_role, extracted_skills)

        logger.debug("Filtered skills (job match): %s", filtered_skills)

    experience = extract_experience(text)

    logger.debug("Parsed experience: %s", experience)

    return {
        "all_skills": extracted_skills,
        "filtered_skills": filtered_skills,
        "experience": experience
    }
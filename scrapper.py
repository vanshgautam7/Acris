import requests
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger("acris.scrapper")
load_dotenv()


def scrape_google_jobs(query, location):

    logger.info(f"Fetching jobs (SerpAPI): {query} {location}")

    jobs = []

    API_KEY = os.getenv("SERPAPI_KEY", "")

    url = "https://serpapi.com/search"

    params = {
        "engine": "google_jobs",
        "q": f"{query} jobs in {location}",
        "hl": "en",
        "gl": "in",   # India
        "api_key": API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)

        logger.debug(f"API Status: {response.status_code}")

        data = response.json()

        results = data.get("jobs_results", [])

        role_words = query.lower().split()

        for job in results:

            title = job.get("title", "").lower()

            if any(word in title for word in role_words):

                link = extract_best_link(job)

                jobs.append({
                    "title": job.get("title", "Job Role"),
                    "company": job.get("company_name", "Company"),
                    "location": job.get("location", location),
                    "link": link
                })

            if len(jobs) >= 10:
                break

        logger.info(f"Jobs fetched: {len(jobs)}")

    except Exception as e:
        logger.error(f"API Error: {e}")

    return jobs


def extract_best_link(job: dict) -> str:
    """
    Extract the best available apply/view link from a SerpAPI job result.

    Priority order:
    1. apply_options[0].link  — direct "Apply" button links (most reliable)
    2. related_links[0].link  — company/job-board page links
    3. job_id-based Google Jobs URL — always works as a fallback
    4. '#' — absolute last resort
    """

    # 1. apply_options (most reliable — LinkedIn, Naukri, Indeed, etc.)
    apply_options = job.get("apply_options", [])
    if apply_options:
        link = apply_options[0].get("link", "").strip()
        if link and link.startswith("http"):
            return link

    # 2. related_links (company site, job board page)
    related_links = job.get("related_links", [])
    if related_links:
        link = related_links[0].get("link", "").strip()
        if link and link.startswith("http"):
            return link

    # 3. Google Jobs URL via job_id (always openable in browser)
    job_id = job.get("job_id", "").strip()
    if job_id:
        return f"https://www.google.com/search?q=jobs&ibp=htl;jobs#fpstate=tldetail&htivrt=jobs&htiq=jobs&htidocid={job_id}"

    # 4. Fallback
    return "#"

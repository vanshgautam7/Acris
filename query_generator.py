# from urllib.parse import quote_plus


# def generate_job_queries(job_role, skills, location):

#     # ---------------- CLEAN INPUT ---------------- #
#     job_role = (job_role or "").strip()
#     location = (location or "").strip()

#     # normalize skills
#     skills = [s.lower().strip() for s in skills if s]

#     # limit to top 5 skills (important for clean queries)
#     skills = skills[:5]

#     # ---------------- BUILD QUERY ---------------- #
#     skill_string = " ".join(skills)

#     if skill_string:
#         query = f"{job_role} {skill_string} jobs in {location}"
#     else:
#         query = f"{job_role} jobs in {location}"

#     # encode for URLs
#     encoded_query = quote_plus(query)

#     # ---------------- GENERATE URLS ---------------- #
#     linkedin_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}"
#     indeed_url = f"https://www.indeed.com/jobs?q={encoded_query}"
#     naukri_url = f"https://www.naukri.com/{encoded_query}-jobs"
#     google_url = f"https://www.google.com/search?q={encoded_query}"

#     # ---------------- RETURN ---------------- #
#     return {
#         "linkedin": linkedin_url,
#         "indeed": indeed_url,
#         "naukri": naukri_url,
#         "google": google_url
#     }





def generate_job_queries(job_role, skills, location):

    queries = []

    # base queries
    queries.append(f"{job_role} {location}")
    queries.append(f"{job_role} jobs {location}")
    queries.append(f"{job_role} hiring {location}")

    # skill-based queries
    for skill in skills[:3]:
        queries.append(f"{job_role} {skill} {location}")

    # experience variations
    queries.append(f"{job_role} fresher {location}")
    queries.append(f"junior {job_role} {location}")

    # fallback (important)
    queries.append(f"{job_role} India")

    return list(set(queries))
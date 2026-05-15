def generate_job_queries(job_role, skills, location):
    queries = []

    queries.append(f"{job_role} {location}")
    queries.append(f"{job_role} jobs {location}")
    queries.append(f"{job_role} hiring {location}")

    for skill in skills[:3]:
        queries.append(f"{job_role} {skill} {location}")

    queries.append(f"{job_role} fresher {location}")
    queries.append(f"junior {job_role} {location}")

    queries.append(f"{job_role} India")

    return list(set(queries))
# G-TEC Developer Practical Exam: Courses API

**Time:** 3 hours
**Allowed:** Internet, official docs, your own notes. AI assistants are allowed, but you must be able to explain every line you submit in the review call.
**Submit:** A link to a GitHub repo (public, or private with access granted) or a zip of this folder.

You are building a small API that G-TEC centres use to publish courses and enroll students. Some of it is already written. You will finish the app, containerize it, set up CI, and explain how you would run it on AWS.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload      # http://localhost:8000/docs
pytest -q
```

Right now most tests fail. That is expected.

---

## Part 1: App development (40 points, about 90 min)

Finish `app/main.py` so that it matches the spec below and **all tests in `tests/test_courses.py` pass**. We also run extra hidden tests against the same spec, so read it carefully and handle the edge cases, not only the visible tests.

### Data

**Course**

| Field | Type | Rules |
|---|---|---|
| `id` | int | Server generated, starts at 1, never reused |
| `title` | string | Required, 3 to 100 characters |
| `description` | string or null | Optional, max 500 characters |
| `fee` | number | Required, 0 or more |
| `duration_weeks` | int | Required, 1 to 52 |
| `capacity` | int | Required, 1 to 500 |
| `enrolled_count` | int | Read only, number of enrollments |
| `created_at` | datetime | Server generated, UTC |

**Enrollment**

| Field | Type | Rules |
|---|---|---|
| `id` | int | Server generated |
| `course_id` | int | From the URL |
| `name` | string | Required, 1 to 100 characters |
| `email` | string | Required, must look like an email. Stored lowercased and trimmed |
| `enrolled_at` | datetime | Server generated, UTC |

### Endpoints

| Method | Path | Success | Errors |
|---|---|---|---|
| GET | `/health` | 200 `{"status": "ok", "version": "<APP_VERSION env var>"}` | |
| GET | `/courses` | 200 `{"items": [...], "total": n, "limit": n, "offset": n}` | 422 on bad params |
| POST | `/courses` | 201 Course | 422 on invalid body |
| GET | `/courses/{id}` | 200 Course | 404 `{"detail": "Course not found"}` |
| PATCH | `/courses/{id}` | 200 Course (partial update, only sent fields change) | 404, 422, 409 (see rules) |
| DELETE | `/courses/{id}` | 204 empty body | 404, 409 (see rules) |
| POST | `/courses/{id}/enrollments` | 201 Enrollment | 404, 422, 409 (see rules) |
| GET | `/courses/{id}/enrollments` | 200 list of Enrollment | 404 |

### Business rules

1. `GET /courses` supports `search` (case-insensitive match on title), `limit` (default 20, min 1, max 100) and `offset` (default 0, min 0). Results are ordered by `id`. `total` is the number of courses **matching the search**, not the page size.
2. Enrolling the same email twice in one course returns **409** `"Already enrolled"`. The check is case-insensitive.
3. Enrolling when the course is at capacity returns **409** `"Course is full"`.
4. PATCH that sets `capacity` lower than the current `enrolled_count` returns **409**.
5. DELETE on a course that has enrollments returns **409**.
6. PATCH uses the same validation rules as create for any field that is sent.

---

## Part 2: Dockerfile (20 points, about 25 min)

Write a `Dockerfile` (and `.dockerignore`) for this app.

- The container must serve the API on port 8000.
- `APP_VERSION` must be settable at **build time** and show up in `/health`.
- Think about image size, security, and how the container behaves when the platform stops it.

Check it works:

```bash
docker build --build-arg APP_VERSION=test123 -t courses-api .
docker run --rm -p 8000:8000 courses-api
curl localhost:8000/health
```

---

## Part 3: GitHub Actions (20 points, about 30 min)

Write `.github/workflows/ci.yml` that:

1. Runs on every pull request and every push to `main`.
2. Lints and runs the tests.
3. Builds the Docker image **only if tests pass**, tagged with the git commit SHA.
4. Proves the built image actually starts and answers `/health`.
5. Bonus: pushes the image to Amazon ECR on pushes to `main` only. You do not need a real AWS account. Write it as you would for production and note any secrets or variables it needs.

---

## Part 4: Deploy to AWS and roll back (20 points, about 30 min)

Write `DEPLOY.md` (1 to 2 pages) answering:

1. Which AWS services would you use to run this in production, and why? Draw or describe the architecture.
2. How does a new commit on `main` get to production? Step by step.
3. How do you know a deploy is healthy?
4. A bad version goes live and users get 500 errors. **How do you roll back**, how long does it take, and how would you make rollback automatic?
5. This app stores data in memory. What problems does that cause once it runs on AWS, and what would you change?

No AWS account needed. We care about your reasoning, not about running it.

---

## Submission checklist

- [ ] `pytest -q` passes
- [ ] `ruff check .` passes
- [ ] `Dockerfile` and `.dockerignore`
- [ ] `.github/workflows/ci.yml`
- [ ] `DEPLOY.md`
- [ ] A short note at the bottom of this README: what you would improve with more time

Good luck!

---

## What I would improve with more time

- **Real persistence.** Replace the in-memory store with PostgreSQL and enforce the duplicate-email and capacity rules with database constraints and transactions, so they hold across multiple instances (details in `DEPLOY.md`).
- **Response models.** Declare Pydantic response schemas so the OpenAPI docs describe the output and responses are validated, instead of returning plain dicts.
- **Stricter email validation.** I used a simple pattern to avoid adding a dependency; `email-validator` (Pydantic `EmailStr`) would be more thorough.
- **Auth.** Creating, editing and deleting courses should require a centre staff login; right now every endpoint is open.
- **Deploy automation.** CI stops at pushing the image. I would add the ECS deploy job with the circuit breaker and alarm-based rollback described in `DEPLOY.md`.
- **Supply chain.** Pin the base image by digest, pin actions by commit SHA, and add an image vulnerability scan to CI.
- **Structure and observability.** Split `main.py` into modules as it grows, and add structured request logs with a request ID.

Decisions I made where the spec was silent: titles and names are trimmed before length checks; a duplicate email is reported before "Course is full"; PATCH rejects `null` for every field except `description`.

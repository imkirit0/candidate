"""Courses API for the G-TEC practical exam. Spec lives in README.md."""

import os
from datetime import UTC, datetime
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field, StringConstraints

APP_VERSION = os.getenv("APP_VERSION", "dev")

# ---------- Schemas ----------
# Field rules are declared once and shared by create and PATCH (business rule 6).

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=100)]
Description = Annotated[str, StringConstraints(max_length=500)]
Fee = Annotated[float, Field(ge=0, allow_inf_nan=False)]
DurationWeeks = Annotated[int, Field(ge=1, le=52)]
Capacity = Annotated[int, Field(ge=1, le=500)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
# "Looks like an email": something@something.tld, no spaces. Trimmed and lowercased
# before the pattern check, so the stored value is already normalised.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


class CourseCreate(BaseModel):
    title: Title
    description: Description | None = None
    fee: Fee
    duration_weeks: DurationWeeks
    capacity: Capacity


class CourseUpdate(BaseModel):
    # Pydantic does not validate defaults, so an omitted field stays None, while an
    # explicit `null` is validated against the non-null type and rejected with 422.
    # Only `description` may be set to null.
    title: Title = None
    description: Description | None = None
    fee: Fee = None
    duration_weeks: DurationWeeks = None
    capacity: Capacity = None


class EnrollmentCreate(BaseModel):
    name: Name
    email: Email


# ---------- In-memory store ----------


class Store:
    def __init__(self) -> None:
        self.lock = Lock()
        self.reset()

    def reset(self) -> None:
        self.courses: dict[int, dict] = {}
        self.enrollments: dict[int, list[dict]] = {}
        self._next_course_id = 1
        self._next_enrollment_id = 1

    def next_course_id(self) -> int:
        cid = self._next_course_id
        self._next_course_id += 1
        return cid

    def next_enrollment_id(self) -> int:
        eid = self._next_enrollment_id
        self._next_enrollment_id += 1
        return eid


store = Store()

app = FastAPI(title="Courses API", version=APP_VERSION)


def _with_count(course: dict) -> dict:
    return {**course, "enrolled_count": len(store.enrollments.get(course["id"], []))}


def _get_or_404(course_id: int) -> dict:
    course = store.courses.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


# ---------- Routes ----------
# Sync handlers run in a thread pool, so every check-then-write holds store.lock.


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}


@app.get("/courses")
def list_courses(
    search: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    with store.lock:
        courses = sorted(store.courses.values(), key=lambda c: c["id"])
        if search:
            needle = search.strip().lower()
            courses = [c for c in courses if needle in c["title"].lower()]
        return {
            "items": [_with_count(c) for c in courses[offset : offset + limit]],
            "total": len(courses),
            "limit": limit,
            "offset": offset,
        }


@app.post("/courses", status_code=201)
def create_course(payload: CourseCreate) -> dict:
    with store.lock:
        course = {
            "id": store.next_course_id(),
            **payload.model_dump(),
            "created_at": datetime.now(UTC),
        }
        store.courses[course["id"]] = course
        return _with_count(course)


@app.get("/courses/{course_id}")
def get_course(course_id: int) -> dict:
    with store.lock:
        return _with_count(_get_or_404(course_id))


@app.patch("/courses/{course_id}")
def update_course(course_id: int, payload: CourseUpdate) -> dict:
    changes = payload.model_dump(exclude_unset=True)  # only fields the client sent
    with store.lock:
        course = _get_or_404(course_id)
        enrolled = len(store.enrollments.get(course_id, []))
        if "capacity" in changes and changes["capacity"] < enrolled:
            raise HTTPException(
                status_code=409, detail="Capacity cannot be lower than enrolled count"
            )
        course.update(changes)
        return _with_count(course)


@app.delete("/courses/{course_id}", status_code=204)
def delete_course(course_id: int) -> Response:
    with store.lock:
        _get_or_404(course_id)
        if store.enrollments.get(course_id):
            raise HTTPException(status_code=409, detail="Course has enrollments")
        del store.courses[course_id]
        store.enrollments.pop(course_id, None)
    return Response(status_code=204)


@app.post("/courses/{course_id}/enrollments", status_code=201)
def enroll(course_id: int, payload: EnrollmentCreate) -> dict:
    with store.lock:
        course = _get_or_404(course_id)
        enrollments = store.enrollments.setdefault(course_id, [])
        # Duplicate is checked before capacity: re-enrolling in a full course is
        # "Already enrolled", which is the more useful answer for that student.
        if any(e["email"] == payload.email for e in enrollments):
            raise HTTPException(status_code=409, detail="Already enrolled")
        if len(enrollments) >= course["capacity"]:
            raise HTTPException(status_code=409, detail="Course is full")
        enrollment = {
            "id": store.next_enrollment_id(),
            "course_id": course_id,
            "name": payload.name,
            "email": payload.email,
            "enrolled_at": datetime.now(UTC),
        }
        enrollments.append(enrollment)
        return enrollment


@app.get("/courses/{course_id}/enrollments")
def list_enrollments(course_id: int) -> list[dict]:
    with store.lock:
        _get_or_404(course_id)
        return list(store.enrollments.get(course_id, []))

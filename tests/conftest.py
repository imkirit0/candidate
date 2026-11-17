import pytest
from fastapi.testclient import TestClient

from app.main import app, store


@pytest.fixture
def client():
    store.reset()
    with TestClient(app) as c:
        yield c
    store.reset()


@pytest.fixture
def course_payload():
    return {
        "title": "Python Full Stack",
        "description": "FastAPI, React and PostgreSQL",
        "fee": 25000,
        "duration_weeks": 12,
        "capacity": 2,
    }


@pytest.fixture
def course(client, course_payload):
    res = client.post("/courses", json=course_payload)
    assert res.status_code == 201, res.text
    return res.json()

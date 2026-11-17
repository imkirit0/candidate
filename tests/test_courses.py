"""Visible tests. The candidate gets this exact file."""


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_create_course(client, course_payload):
    res = client.post("/courses", json=course_payload)
    assert res.status_code == 201
    body = res.json()
    assert body["id"] == 1
    assert body["title"] == course_payload["title"]
    assert body["enrolled_count"] == 0
    assert "created_at" in body


def test_create_course_validation(client, course_payload):
    bad_cases = [
        {**course_payload, "title": "ab"},
        {**course_payload, "fee": -1},
        {**course_payload, "duration_weeks": 0},
        {**course_payload, "duration_weeks": 53},
        {**course_payload, "capacity": 0},
    ]
    for payload in bad_cases:
        assert client.post("/courses", json=payload).status_code == 422, payload


def test_get_course(client, course):
    res = client.get(f"/courses/{course['id']}")
    assert res.status_code == 200
    assert res.json()["title"] == course["title"]


def test_get_missing_course_returns_404(client):
    res = client.get("/courses/999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Course not found"


def test_list_courses_with_pagination(client, course_payload):
    for i in range(5):
        client.post("/courses", json={**course_payload, "title": f"Course {i}"})
    res = client.get("/courses", params={"limit": 2, "offset": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 5
    assert [c["title"] for c in body["items"]] == ["Course 1", "Course 2"]


def test_search_courses(client, course_payload):
    client.post("/courses", json={**course_payload, "title": "Data Science"})
    client.post("/courses", json={**course_payload, "title": "Web Design"})
    res = client.get("/courses", params={"search": "data"})
    assert [c["title"] for c in res.json()["items"]] == ["Data Science"]


def test_patch_course(client, course):
    res = client.patch(f"/courses/{course['id']}", json={"fee": 30000})
    assert res.status_code == 200
    assert res.json()["fee"] == 30000
    assert res.json()["title"] == course["title"]


def test_delete_course(client, course):
    assert client.delete(f"/courses/{course['id']}").status_code == 204
    assert client.get(f"/courses/{course['id']}").status_code == 404


def test_enroll_student(client, course):
    res = client.post(
        f"/courses/{course['id']}/enrollments",
        json={"name": "Asha", "email": "asha@example.com"},
    )
    assert res.status_code == 201
    assert res.json()["course_id"] == course["id"]
    assert client.get(f"/courses/{course['id']}").json()["enrolled_count"] == 1


def test_enroll_rejects_duplicate_email(client, course):
    url = f"/courses/{course['id']}/enrollments"
    client.post(url, json={"name": "Asha", "email": "asha@example.com"})
    res = client.post(url, json={"name": "Asha", "email": "asha@example.com"})
    assert res.status_code == 409


def test_enroll_rejects_when_full(client, course):
    url = f"/courses/{course['id']}/enrollments"
    client.post(url, json={"name": "A", "email": "a@example.com"})
    client.post(url, json={"name": "B", "email": "b@example.com"})
    res = client.post(url, json={"name": "C", "email": "c@example.com"})
    assert res.status_code == 409
    assert res.json()["detail"] == "Course is full"


def test_list_enrollments(client, course):
    url = f"/courses/{course['id']}/enrollments"
    client.post(url, json={"name": "A", "email": "a@example.com"})
    res = client.get(url)
    assert res.status_code == 200
    assert len(res.json()) == 1

"""Extra tests for spec rules the visible tests do not cover."""


def test_ids_are_never_reused(client, course_payload):
    first = client.post("/courses", json=course_payload).json()
    client.delete(f"/courses/{first['id']}")
    assert client.post("/courses", json=course_payload).json()["id"] == first["id"] + 1


def test_list_params_validation_and_defaults(client, course_payload):
    client.post("/courses", json=course_payload)
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "x"}):
        assert client.get("/courses", params=params).status_code == 422, params
    body = client.get("/courses").json()
    assert (body["limit"], body["offset"], body["total"]) == (20, 0, 1)


def test_total_counts_search_matches_not_page(client, course_payload):
    for title in ("Data One", "Data Two", "Web Design"):
        client.post("/courses", json={**course_payload, "title": title})
    body = client.get("/courses", params={"search": "DATA", "limit": 1}).json()
    assert body["total"] == 2
    assert len(body["items"]) == 1


def test_create_boundaries(client, course_payload):
    ok = {"title": "abc", "fee": 0, "duration_weeks": 52, "capacity": 500}
    assert client.post("/courses", json=ok).status_code == 201
    bad_cases = [
        {**course_payload, "title": "x" * 101},
        {**course_payload, "description": "x" * 501},
        {**course_payload, "capacity": 501},
        {k: v for k, v in course_payload.items() if k != "fee"},
    ]
    for payload in bad_cases:
        assert client.post("/courses", json=payload).status_code == 422, payload


def test_patch_rules(client, course):
    url = f"/courses/{course['id']}"
    assert client.patch("/courses/999", json={"fee": 1}).status_code == 404
    for body in ({"title": "ab"}, {"fee": -1}, {"capacity": 0}, {"title": None}):
        assert client.patch(url, json=body).status_code == 422, body
    # description is the only nullable field, and other fields stay untouched
    res = client.patch(url, json={"description": None})
    assert res.json()["description"] is None
    assert res.json()["fee"] == course["fee"]


def test_patch_capacity_below_enrolled_is_409(client, course):
    url = f"/courses/{course['id']}"
    client.post(f"{url}/enrollments", json={"name": "A", "email": "a@example.com"})
    client.post(f"{url}/enrollments", json={"name": "B", "email": "b@example.com"})
    assert client.patch(url, json={"capacity": 1}).status_code == 409
    assert client.patch(url, json={"capacity": 2}).status_code == 200


def test_delete_rules(client, course):
    url = f"/courses/{course['id']}"
    assert client.delete("/courses/999").status_code == 404
    client.post(f"{url}/enrollments", json={"name": "A", "email": "a@example.com"})
    assert client.delete(url).status_code == 409
    assert client.get(url).status_code == 200


def test_enrollment_email_rules(client, course):
    url = f"/courses/{course['id']}/enrollments"
    res = client.post(url, json={"name": "Asha", "email": "  Asha@Example.COM "})
    assert res.status_code == 201
    assert res.json()["email"] == "asha@example.com"
    dup = client.post(url, json={"name": "Asha", "email": "ASHA@example.com"})
    assert dup.status_code == 409
    assert dup.json()["detail"] == "Already enrolled"
    for body in ({"name": "X", "email": "nope"}, {"name": "", "email": "x@example.com"}):
        assert client.post(url, json=body).status_code == 422, body


def test_enrollments_on_missing_course_are_404(client):
    body = {"name": "A", "email": "a@example.com"}
    assert client.post("/courses/999/enrollments", json=body).status_code == 404
    assert client.get("/courses/999/enrollments").status_code == 404

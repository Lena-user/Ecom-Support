"""Test CRUD /api/support/kb — quản lý Knowledge Base qua UI (ghi thẳng vào Qdrant, cần role admin)."""


def test_kb_crud_roundtrip(client, admin_auth_headers):
    create_resp = client.post(
        "/api/support/kb",
        json={"source": "Test Source", "content": "Nội dung tài liệu test"},
        headers=admin_auth_headers,
    )
    assert create_resp.status_code == 200
    doc = create_resp.json()
    doc_id = doc["id"]
    assert doc["source"] == "Test Source"

    list_resp = client.get("/api/support/kb", headers=admin_auth_headers)
    assert list_resp.status_code == 200
    assert any(d["id"] == doc_id for d in list_resp.json())

    update_resp = client.put(
        f"/api/support/kb/{doc_id}",
        json={"source": "Test Source (sửa)", "content": "Nội dung đã sửa"},
        headers=admin_auth_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["content"] == "Nội dung đã sửa"

    list_after_update = client.get("/api/support/kb", headers=admin_auth_headers).json()
    updated_doc = next(d for d in list_after_update if d["id"] == doc_id)
    assert updated_doc["content"] == "Nội dung đã sửa"
    assert updated_doc["source"] == "Test Source (sửa)"

    delete_resp = client.delete(f"/api/support/kb/{doc_id}", headers=admin_auth_headers)
    assert delete_resp.status_code == 200

    list_after_delete = client.get("/api/support/kb", headers=admin_auth_headers).json()
    assert all(d["id"] != doc_id for d in list_after_delete)


def test_list_kb_empty_by_default(client, admin_auth_headers):
    resp = client.get("/api/support/kb", headers=admin_auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_kb_requires_admin_role(client, staff_auth_headers):
    resp = client.get("/api/support/kb", headers=staff_auth_headers)
    assert resp.status_code == 403

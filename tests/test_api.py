from __future__ import annotations

import io

import fitz


def make_pdf() -> bytes:
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    doc = fitz.open()
    page = doc.new_page()
    lines = [
        "THÔNG TƯ 01/2024/TT-NHNN",
        "CHƯƠNG I",
        "NHỮNG QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Thông tư này quy định về điều kiện cấp tín dụng của tổ chức tín dụng.",
        "Điều 5. Điều kiện cấp tín dụng",
        "1. Khách hàng phải có năng lực pháp luật dân sự.",
        "a) Đối với cá nhân: đủ 18 tuổi.",
        "2. Khách hàng phải có năng lực hành vi dân sự đầy đủ.",
        "Điều 6. Hồ sơ đề nghị cấp tín dụng",
        "1. Giấy đề nghị cấp tín dụng theo mẫu.",
        "2. Tài liệu chứng minh mục đích sử dụng vốn.",
    ]
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11, fontname="DejaVu", fontfile=font_path)
        y += 22
    payload = doc.tobytes()
    doc.close()
    return payload


def test_upload_process_search_chat_and_audit(admin_client):
    client = admin_client
    pdf = make_pdf()

    response = client.post(
        "/api/documents/upload",
        files={"file": ("thong-tu-01-2024.pdf", pdf, "application/pdf")},
        data={"title": "Thông tư 01/2024/TT-NHNN"},
    )
    assert response.status_code == 201, response.text
    document = response.json()
    document_id = document["id"]
    assert document["status"] == "processing"

    # The/session worker is disabled in tests; run one queued job synchronously.
    from app.worker import process_one

    assert process_one() is True

    detail = client.get(f"/api/documents/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "ready"
    assert detail.json()["page_count"] == 1

    search = client.post(
        "/api/search",
        json={"query": "năng lực pháp luật dân sự", "top_k": 5},
    )
    assert search.status_code == 200, search.text
    results = search.json()["results"]
    assert results, search.text
    assert any("Điều 5" in result["legal_path"] for result in results)

    chat = client.post(
        "/api/chat",
        json={"message": "Điều kiện cấp tín dụng là gì?", "top_k": 5, "generate_answer": True},
    )
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["sources"]
    assert payload["answer"]
    assert not payload["abstained"]
    assert payload["citations"]

    # Admin document view must be audited.
    file_response = client.get(f"/api/documents/{document_id}/file")
    assert file_response.status_code == 200
    audit = client.get("/api/admin/audit")
    assert audit.status_code == 200
    actions = [event["action"] for event in audit.json()]
    assert "document.admin_view" in actions

    stats = client.get("/api/admin/stats")
    assert stats.status_code == 200
    assert stats.json()["documents"] >= 1
    assert stats.json()["chunks"] >= 1

    duplicate = client.post(
        "/api/documents/upload",
        files={"file": ("thong-tu-01-2024.pdf", pdf, "application/pdf")},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == document_id

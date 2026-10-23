from __future__ import annotations

from app.services.extraction import ExtractedPage, _scale_ocr_bboxes
from app.services.ingestion import _guess_metadata
from app.services.parser import SourceLine


def test_ocr_bboxes_are_converted_from_pixels_to_pdf_points():
    lines = [SourceLine(text="Điều 1", page_number=0, bbox=[100.0, 200.0, 300.0, 400.0])]

    # A 1000x2000px OCR image for a 500x1000pt page.
    _scale_ocr_bboxes(lines, 1000, 2000, 500.0, 1000.0)

    assert lines[0].bbox == [50.0, 100.0, 150.0, 200.0]


def test_metadata_uses_descriptive_title_after_document_type():
    page = ExtractedPage(
        page_number=1,
        width=595,
        height=842,
        text="\n".join(
            [
                "NGÂN HÀNG NHÀ NƯỚC VIỆT NAM",
                "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
                "Số: 01/2024/TT-NHNN",
                "Hà Nội, ngày 01 tháng 01 năm 2024",
                "THÔNG TƯ",
                "Quy định về điều kiện cấp tín dụng của tổ chức tín dụng",
                "CHƯƠNG I",
                "Điều 1. Phạm vi điều chỉnh",
            ]
        ),
        lines=[],
    )

    metadata = _guess_metadata([page], "thong-tu-01-2024")

    assert metadata["document_number"] == "01/2024/TT-NHNN"
    assert metadata["document_type"] == "Thông Tư"
    assert metadata["title"] == "Quy định về điều kiện cấp tín dụng của tổ chức tín dụng"

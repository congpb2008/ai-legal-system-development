from app.services.chunking import build_chunks
from app.services.parser import SourceLine, parse_legal_structure


def line(text: str, page: int = 1) -> SourceLine:
    return SourceLine(text=text, page_number=page, bbox=[10, 10, 500, 30])


def test_parse_vietnamese_legal_hierarchy():
    pages = [
        (
            1,
            [
                line("CHƯƠNG I"),
                line("NHỮNG QUY ĐỊNH CHUNG"),
                line("Điều 1. Phạm vi điều chỉnh"),
                line("Thông tư này quy định về hoạt động cấp tín dụng."),
                line("Điều 2. Đối tượng áp dụng"),
                line("1. Tổ chức tín dụng."),
                line("a) Ngân hàng thương mại."),
                line("b) Chi nhánh ngân hàng nước ngoài."),
                line("2. Khách hàng."),
                line("CHƯƠNG II"),
                line("ĐIỀU KIỆN CẤP TÍN DỤNG"),
                line("Điều 3. Điều kiện cấp tín dụng"),
                line("1. Có năng lực pháp luật dân sự."),
            ],
        )
    ]

    nodes = parse_legal_structure(pages)
    articles = [node for node in nodes if node.level == "article"]
    clauses = [node for node in nodes if node.level == "clause"]
    points = [node for node in nodes if node.level == "point"]

    assert [node.number for node in articles] == ["1", "2", "3"]
    assert articles[2].title == "Điều kiện cấp tín dụng"
    assert articles[2].path == "Chương II > Điều 3"
    assert len(clauses) == 3
    assert clauses[0].path == "Chương I > Điều 2 > Khoản 1"
    assert len(points) == 2
    assert points[0].path == "Chương I > Điều 2 > Khoản 1 > Điểm a"


def test_chunks_include_parent_context():
    pages = [
        (
            1,
            [
                line("Điều 5. Điều kiện cấp tín dụng"),
                line("1. Khách hàng phải có năng lực pháp luật dân sự."),
                line("a) Đối với cá nhân: đủ 18 tuổi."),
            ],
        )
    ]
    nodes = parse_legal_structure(pages)
    chunks = build_chunks(nodes, "Thông tư 01/2024/TT-NHNN")
    assert any("Điều 5" in chunk.context_text for chunk in chunks)
    assert any("Điểm a" in chunk.context_text for chunk in chunks)
    assert all(chunk.text for chunk in chunks)


def test_toc_pages_are_skipped():
    pages = [
        (
            1,
            [
                line("MỤC LỤC"),
                line("Điều 1. Phạm vi điều chỉnh ........ 1"),
                line("Điều 2. Đối tượng áp dụng ........ 2"),
            ],
        ),
        (
            2,
            [
                line("Điều 1. Phạm vi điều chỉnh"),
                line("Nội dung thật."),
            ],
        ),
    ]
    nodes = parse_legal_structure(pages)
    assert len([node for node in nodes if node.level == "article"]) == 1
    assert nodes[0].page_start == 2

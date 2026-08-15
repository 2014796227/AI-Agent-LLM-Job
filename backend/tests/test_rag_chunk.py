import fitz
from app.rag import chunk_pdf

def _make_pdf(pages_text: list, path):
    doc = fitz.open()
    for txt in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), txt, fontsize=12)
    doc.save(path)
    doc.close()

def test_chunk_never_crosses_page(tmp_path):
    p = tmp_path / "t.pdf"
    _make_pdf(["A" * 100 + "\nB" * 100,
               "C" * 400 + "\nD" * 100], str(p))
    chunks = chunk_pdf(str(p), size=600, overlap=80)
    assert chunks
    for c in chunks:
        assert c["page"] in (1, 2)
        has_a = "A" * 10 in c["chunk"]
        has_c = "C" * 10 in c["chunk"]
        assert not (has_a and has_c), "chunk 不得跨页"

def test_chunk_page_attribution(tmp_path):
    # v19 修正：原 15 字符文本 < chunk_pdf 的 20 字符"无文本层"阈值，
    # 测试数据自己触发扫描页拒绝；加长到阈值以上，语义不变
    p = tmp_path / "t2.pdf"
    _make_pdf(["first page text padded to threshold",
               "second page text padded to threshold"], str(p))
    chunks = chunk_pdf(str(p), size=600)
    assert any("first page" in c["chunk"] and c["page"] == 1
               for c in chunks)
    assert any("second page" in c["chunk"] and c["page"] == 2
               for c in chunks)

def test_scanned_page_rejected(tmp_path):
    p = tmp_path / "t3.pdf"
    doc = fitz.open()
    doc.new_page()          # 空白页=无文本层
    doc.save(str(p))
    doc.close()
    try:
        chunk_pdf(str(p))
        assert False, "应拒绝扫描/空页"
    except ValueError as e:
        assert "无文本层" in str(e)

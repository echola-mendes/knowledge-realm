from app.chunk import CHUNK_OVERLAP, CHUNK_SIZE, split_markdown


def test_two_headings_over_limit_yields_multiple_chunks():
    first = "甲" * 900
    second = "乙" * 200
    md = f"# 标题一\n\n{first}\n\n# 标题二\n\n{second}"
    chunks = split_markdown(md)
    assert len(chunks) > 1
    for item in chunks[:-1]:
        assert len(item.content) <= CHUNK_SIZE
    long_parts = [c.content for c in chunks if "甲" in c.content]
    assert len(long_parts) >= 2
    left, right = long_parts[0], long_parts[1]
    assert left[-CHUNK_OVERLAP:] == right[:CHUNK_OVERLAP]
    headings = {c.heading for c in chunks if c.heading}
    assert "标题一" in headings
    assert "标题二" in headings


def test_empty_markdown_zero_chunks():
    assert split_markdown("") == []
    assert split_markdown("   \n\t") == []

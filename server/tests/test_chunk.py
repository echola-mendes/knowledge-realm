from app.ingest.chunk import CHUNK_OVERLAP, CHUNK_SIZE, split_markdown, split_markdown_sections


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
    assert split_markdown_sections("") == []


def test_short_section_child_only_no_parent():
    md = "# 短节\n\n" + ("短" * 100)
    sections = split_markdown_sections(md)
    assert len(sections) == 1
    assert sections[0].parent is None
    assert len(sections[0].children) == 1
    assert sections[0].children[0].heading == "短节"


def test_long_section_parent_and_multiple_children():
    body = "甲" * 900
    md = f"# 长节\n\n{body}"
    sections = split_markdown_sections(md)
    assert len(sections) == 1
    sec = sections[0]
    assert sec.parent is not None
    assert len(sec.children) >= 2
    assert body in sec.parent.content
    for child in sec.children:
        assert child.content in sec.parent.content
    long_parts = [c.content for c in sec.children if "甲" in c.content]
    assert len(long_parts) >= 2
    left, right = long_parts[0], long_parts[1]
    assert left[-CHUNK_OVERLAP:] == right[:CHUNK_OVERLAP]


def test_oversized_table_single_child_no_parent():
    # Same strategy as before: protected table longer than chunk_size stays one piece.
    header = "| a | b |\n|---|---|\n"
    rows = "".join(f"| {'x' * 40} | {'y' * 40} |\n" for _ in range(30))
    md = f"# 表节\n\n{header}{rows}"
    assert len(md) > CHUNK_SIZE
    sections = split_markdown_sections(md)
    assert len(sections) == 1
    assert sections[0].parent is None
    assert len(sections[0].children) == 1
    assert "|" in sections[0].children[0].content

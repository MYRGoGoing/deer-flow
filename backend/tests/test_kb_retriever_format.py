from deerflow.community.kb_search.retriever import format_results


def test_format_results_includes_file_page_and_content_type():
    rendered = format_results(
        [
            {
                "doc_title": "Maintenance Manual",
                "section_path": "Torque Table",
                "source": "",
                "source_file": "platform/manual.pdf",
                "page_number": 8,
                "slide_number": None,
                "content_type": "table",
                "weak_evidence": False,
                "text": "| Bolt | Torque |",
            }
        ]
    )

    assert "来源: platform/manual.pdf，第 8 页，表格" in rendered


def test_format_results_includes_slide_number_and_weak_marker():
    rendered = format_results(
        [
            {
                "doc_title": "Deployment Slides",
                "section_path": "HA Mode",
                "source": "",
                "source_file": "baas/deployment.pptx",
                "page_number": None,
                "slide_number": 3,
                "content_type": "text",
                "weak_evidence": True,
                "text": "Use three nodes.",
            }
        ]
    )

    assert "HA Mode [弱证据]" in rendered
    assert "来源: baas/deployment.pptx，第 3 张幻灯片" in rendered


def test_format_results_labels_ocr_and_image_content():
    base = {
        "doc_title": "故障手册",
        "section_path": "故障定位",
        "source": "",
        "source_file": "manual.pdf",
        "page_number": 2,
        "slide_number": None,
        "weak_evidence": False,
        "text": "E102",
    }

    rendered = format_results(
        [
            {**base, "content_type": "ocr"},
            {
                **base,
                "source_file": "slides.pptx",
                "page_number": None,
                "slide_number": 3,
                "content_type": "image",
            },
        ]
    )

    assert "manual.pdf，第 2 页，OCR" in rendered
    assert "slides.pptx，第 3 张幻灯片，图片描述" in rendered


def test_format_results_prefers_expanded_context():
    rendered = format_results(
        [
            {
                "doc_title": "HVM 开发手册",
                "section_path": "合约入口",
                "source": "",
                "source_file": "hvm/development.md",
                "page_number": None,
                "slide_number": None,
                "content_type": "text",
                "weak_evidence": False,
                "text": "以注解声明合约入口与可调用方法。",
                "context_text": ("以注解声明合约入口与可调用方法。\n\n[相邻章节：合约基本结构]\n使用 @Contract 声明合约，使用 @Transaction 声明可调用方法。"),
            }
        ]
    )

    assert "@Contract" in rendered
    assert "@Transaction" in rendered
    assert "[相邻章节：合约基本结构]" in rendered

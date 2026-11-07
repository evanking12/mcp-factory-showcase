from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_interwoven_product_transfer_review_is_explicit_and_bounded() -> None:
    review_path = (
        ROOT
        / "docs"
        / "architecture"
        / "engineScaling"
        / "engineScaling_Interwoven"
        / "INTERWOVEN-PRODUCT-TRANSFER-REVIEW.md"
    )
    text = review_path.read_text(encoding="utf-8")

    assert "The chosen harder proving family is:" in text
    assert "mainframe COBOL transaction package pilot" in text
    assert "## What Transfers Cleanly" in text
    assert "## What Remains Contoso-Shaped" in text
    assert "## Next Bounded Move" in text
    assert "adapter-free at first" in text

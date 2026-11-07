from __future__ import annotations

from api.pipeline.core.prompts import _normalize_behavioral_spec_typing_imports


def test_normalize_behavioral_spec_injects_optional_import() -> None:
    content = (
        '"""Example wrapper."""\n\n'
        "class Example:\n"
        "    def run(self, value: Optional[str]) -> int:\n"
        "        return 0\n"
    )

    normalized = _normalize_behavioral_spec_typing_imports(content)

    assert 'from typing import Optional' in normalized
    assert normalized.index('from typing import Optional') > normalized.index('"""Example wrapper."""')


def test_normalize_behavioral_spec_keeps_existing_optional_import() -> None:
    content = (
        "from __future__ import annotations\n"
        "from typing import Optional\n\n"
        "class Example:\n"
        "    def run(self, value: Optional[str]) -> int:\n"
        "        return 0\n"
    )

    normalized = _normalize_behavioral_spec_typing_imports(content)

    assert normalized.count("from typing import Optional") == 1


def test_normalize_behavioral_spec_skips_typing_optional_usage() -> None:
    content = (
        "class Example:\n"
        "    def run(self, value: typing.Optional[str]) -> int:\n"
        "        return 0\n"
    )

    normalized = _normalize_behavioral_spec_typing_imports(content)

    assert "from typing import Optional" not in normalized


def test_normalize_behavioral_spec_is_idempotent() -> None:
    content = (
        '"""Example wrapper."""\n\n'
        "class Example:\n"
        "    def run(self, value: Optional[str]) -> int:\n"
        "        return 0\n"
    )

    normalized = _normalize_behavioral_spec_typing_imports(content)
    renormalized = _normalize_behavioral_spec_typing_imports(normalized)

    assert normalized == renormalized

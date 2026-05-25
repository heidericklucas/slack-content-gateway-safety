"""Tests for warning template rendering."""

from __future__ import annotations

import pytest

from app.schemas import Category
from app.slack.warnings import render_warning


@pytest.mark.parametrize("category", list(Category))
def test_every_category_renders(category: Category) -> None:
    msg = render_warning(category, "U123")
    assert "<@U123>" in msg


def test_threat_template_uses_rotating_light() -> None:
    assert render_warning(Category.THREAT, "U1").startswith(":rotating_light:")


def test_other_templates_use_warning() -> None:
    for category in Category:
        if category is Category.THREAT:
            continue
        assert render_warning(category, "U1").startswith(":warning:")

"""Tests for services.shared.text_masking.mask_email."""

from services.shared.text_masking import mask_email


def test_mask_email_full_local_part_returns_first_char_starred() -> None:
    assert mask_email("john.doe@example.com") == "j***@example.com"


def test_mask_email_single_char_local_part_returns_star_at_domain() -> None:
    assert mask_email("a@example.com") == "*@example.com"


def test_mask_email_empty_local_part_returns_redacted() -> None:
    assert mask_email("@example.com") == "[REDACTED]"


def test_mask_email_no_at_sign_returns_redacted() -> None:
    assert mask_email("noemail") == "[REDACTED]"


def test_mask_email_empty_string_returns_redacted() -> None:
    assert mask_email("") == "[REDACTED]"


def test_mask_email_whitespace_stripped_before_masking() -> None:
    assert mask_email("  jane@test.co.uk  ") == "j***@test.co.uk"


def test_mask_email_local_part_with_dots_returns_first_char_starred() -> None:
    assert mask_email("j.d@x.co") == "j***@x.co"


def test_mask_email_multiple_at_signs_splits_on_rightmost() -> None:
    assert mask_email("a@b@example.com") == "a***@example.com"

"""Tests for services.shared.text_masking.mask_email."""

from services.shared.text_masking import mask_email, mask_pan


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


def test_mask_pan_sixteen_digits_returns_grouped_mask() -> None:
    assert mask_pan("4111111111111111") == "**** **** **** 1111"


def test_mask_pan_fifteen_digits_amex_style_returns_grouped_mask() -> None:
    assert mask_pan("412345678901234") == "**** **** *** 1234"


def test_mask_pan_thirteen_digits_returns_grouped_mask() -> None:
    assert mask_pan("1234567890123") == "**** **** * 0123"


def test_mask_pan_exactly_four_digits_returns_last4_only() -> None:
    assert mask_pan("1111") == "1111"


def test_mask_pan_five_digits_returns_single_star_and_last4() -> None:
    assert mask_pan("12345") == "* 2345"


def test_mask_pan_all_zeros_sixteen_digits_returns_grouped_mask() -> None:
    assert mask_pan("0000000000000000") == "**** **** **** 0000"


def test_mask_pan_spaces_present_returns_grouped_mask() -> None:
    assert mask_pan("1111 1111 1111 1111") == "**** **** **** 1111"


def test_mask_pan_hyphens_present_returns_grouped_mask() -> None:
    assert mask_pan("4111-1111-1111-1111") == "**** **** **** 1111"


def test_mask_pan_letter_present_returns_redacted() -> None:
    assert mask_pan("1a34") == "[REDACTED]"


def test_mask_pan_dots_present_returns_redacted() -> None:
    assert mask_pan("1.234.567.890.1234") == "[REDACTED]"


def test_mask_pan_empty_string_returns_redacted() -> None:
    assert mask_pan("") == "[REDACTED]"


def test_mask_pan_only_spaces_returns_redacted() -> None:
    assert mask_pan("   ") == "[REDACTED]"


def test_mask_pan_three_digits_returns_redacted() -> None:
    assert mask_pan("123") == "[REDACTED]"

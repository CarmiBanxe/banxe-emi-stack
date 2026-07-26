"""Log-safe text masking helpers."""


def mask_email(value: str) -> str:
    stripped = value.strip()
    if not stripped or "@" not in stripped:
        return "[REDACTED]"

    local_part, domain = stripped.rsplit("@", 1)
    if not local_part:
        return "[REDACTED]"

    if len(local_part) == 1:
        return f"*@{domain}"

    return f"{local_part[0]}***@{domain}"


def mask_pan(value: str) -> str:
    stripped = value.strip()
    normalized = stripped.replace(" ", "").replace("-", "")
    if len(normalized) < 4 or not normalized.isdigit():
        return "[REDACTED]"

    last4 = normalized[-4:]
    masked_len = len(normalized) - 4
    if masked_len == 0:
        return last4

    masked = "*" * masked_len
    groups = [masked[i : i + 4] for i in range(0, masked_len, 4)]
    return f"{' '.join(groups)} {last4}"

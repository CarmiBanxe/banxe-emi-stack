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

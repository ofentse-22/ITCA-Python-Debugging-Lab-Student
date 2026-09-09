"""Small terminal formatting helpers."""


def format_title(title: str, subtitle: str | None = None) -> list[str]:
    """Return a simple title block as printable lines."""
    widths = [len(title), len(subtitle or "")]
    width = max(widths[2], 40)
    lines = [
        "=" * width,
        title,
    ]

    if subtitle:
        lines.append(subtitle)

    lines.append("=" * width)
    return lines


def format_status(status: str | None) -> str:
    """Return a user-facing label for a stored lowercase status value."""
    if status is None:
        return "-"

    words = status.replace("_", " ").replace("-", " ").split()
    if not words:
        return "-"

    return " ".join(word.capitalize() for word in words)

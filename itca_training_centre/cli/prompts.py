"""Reusable prompt helpers for CLI input."""

from collections.abc import Callable, Iterable


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]

CANCEL_COMMAND = "q"


def read_menu_choice(prompt: str, input_func: InputFunction = input) -> str:
    """Read and normalize a menu choice.

    End-of-file input is treated as a clean exit request. This keeps scripted
    smoke tests and redirected terminal sessions from crashing unexpectedly.
    """
    try:
        return input_func(prompt).strip()
    except EOFError:
        return "0"


def is_valid_menu_choice(choice: str, valid_choices: Iterable[str]) -> bool:
    """Return True when the choice is one of the allowed menu values."""
    return choice in set(valid_choices)


def read_text(prompt: str, input_func: InputFunction = input) -> str:
    """Read free text, treating EOF as the standard cancel command."""
    try:
        return input_func(prompt)
    except EOFError:
        return CANCEL_COMMAND


def is_cancel(value: str) -> bool:
    """Return True when a typed value means cancel this workflow."""
    return value.strip().lower() == CANCEL_COMMAND


def prompt_required(
    prompt: str,
    input_func: InputFunction = input,
    output_func: OutputFunction = print,
) -> str | None:
    """Prompt until a non-empty value is supplied, or return None on cancel."""
    while True:
        value = read_text(prompt, input_func)
        if is_cancel(value):
            return None
        if value.strip():
            return value.strip()
        output_func("This value is required.")


def prompt_optional(
    prompt: str,
    input_func: InputFunction = input,
) -> str | None:
    """Prompt for an optional value, returning q when the user cancels."""
    value = read_text(prompt, input_func)
    if is_cancel(value):
        return CANCEL_COMMAND

    return value.strip()


def prompt_yes_no(
    prompt: str,
    input_func: InputFunction = input,
    output_func: OutputFunction = print,
    default: bool = False,
) -> bool | None:
    """Read a y/n answer, returning None when the user cancels."""
    while True:
        value = read_text(prompt, input_func).strip().lower()
        if is_cancel(value):
            return None
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        output_func("Please enter y or n.")


def confirm(
    prompt: str,
    input_func: InputFunction = input,
    output_func: OutputFunction = print,
) -> bool:
    """Return True only for an explicit yes answer."""
    return bool(prompt_yes_no(prompt, input_func, output_func, default=False))

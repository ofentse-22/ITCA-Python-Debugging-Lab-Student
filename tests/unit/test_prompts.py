"""Tests for CLI prompt helpers."""

import unittest

from itca_training_centre.cli.prompts import (
    confirm,
    is_valid_menu_choice,
    prompt_optional,
    prompt_required,
    prompt_yes_no,
    read_menu_choice,
    read_text,
)


class PromptTests(unittest.TestCase):
    def test_read_menu_choice_strips_input(self):
        choice = read_menu_choice("Select: ", input_func=lambda prompt: "  10  ")

        self.assertEqual("10", choice)

    def test_read_menu_choice_treats_eof_as_exit(self):
        def raise_eof(prompt):
            raise EOFError

        choice = read_menu_choice("Select: ", input_func=raise_eof)

        self.assertEqual("0", choice)

    def test_is_valid_menu_choice(self):
        self.assertTrue(is_valid_menu_choice("1", ("1", "2", "0")))
        self.assertFalse(is_valid_menu_choice("x", ("1", "2", "0")))

    def test_read_text_treats_eof_as_cancel(self):
        def raise_eof(prompt):
            raise EOFError

        self.assertEqual("q", read_text("Value: ", input_func=raise_eof))

    def test_prompt_required_retries_blanks_and_strips_result(self):
        choices = iter(["", "  STU-1001  "])
        output = []

        value = prompt_required(
            "Student number: ",
            input_func=lambda prompt: next(choices),
            output_func=output.append,
        )

        self.assertEqual("STU-1001", value)
        self.assertEqual(["This value is required."], output)

    def test_prompt_optional_returns_none_or_cancel(self):
        self.assertIsNone(prompt_optional("Email [leave blank to skip]: ", input_func=lambda prompt: ""))
        self.assertEqual("q", prompt_optional("Email [leave blank to skip]: ", input_func=lambda prompt: " q "))

    def test_prompt_yes_no_accepts_expected_values_and_reprompts_invalid_input(self):
        choices = iter(["maybe", "yes"])
        output = []

        result = prompt_yes_no(
            "Proceed? [y/N]: ",
            input_func=lambda prompt: next(choices),
            output_func=output.append,
        )

        self.assertTrue(result)
        self.assertEqual(["Please enter y or n."], output)

    def test_confirm_requires_explicit_yes(self):
        self.assertFalse(confirm("Proceed? [y/N]: ", input_func=lambda prompt: ""))
        self.assertTrue(confirm("Proceed? [y/N]: ", input_func=lambda prompt: "y"))


if __name__ == "__main__":
    unittest.main()

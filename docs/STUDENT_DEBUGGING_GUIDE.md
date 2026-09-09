# Student Debugging Guide

Work in small cycles. A traceback usually gives you the file, line, and exception type to inspect first.

## Useful Commands

```powershell
py -m compileall -q .
py -m unittest discover -s tests
py -m unittest tests.unit.test_course_model
```

## Debugging Habits

- Read the failing test before changing code.
- Check spelling, indentation, imports, and function calls before deeper logic.
- Print or inspect values at boundaries between CLI, service, repository, and model code.
- Use small disposable data files for import, export, backup, and restore workflows.
- After a fix, run a nearby test and then the broader suite.

## Concepts To Revisit

- Strings, numbers, Decimal values, and type conversion.
- Lists, tuples, dictionaries, sets, and row shapes.
- Conditions, loops, return values, scope, and function arguments.
- Classes, dataclasses, properties, and module imports.
- File handling, path validation, exceptions, SQLite queries, and transactions.

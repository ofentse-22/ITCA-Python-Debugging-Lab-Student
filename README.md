# ITCA Training Centre Debugging Lab

This repository contains a deliberately faulty Python command-line application for practicing Python fundamentals in a realistic training-centre system.

## Learning Goals

- Read tracebacks and connect them to source files.
- Separate syntax, import, validation, data, file, exception, and SQLite failures.
- Make small code changes and confirm each change with the public tests.
- Explain what you changed and why the behavior improved.

## Run The Application

```powershell
py -m itca_training_centre
```

The application is expected to fail at first. Use the failure details as the start of your investigation.

## Run Checks

```powershell
py -m compileall -q .
py -m unittest discover -s tests
```

Run focused checks while working, then run the full public test suite before submitting your work.

## Suggested Workflow

1. Create a working branch.
2. Reproduce one failure.
3. Read the nearby code and related test.
4. Make the smallest useful change.
5. Run the check again.
6. Commit when the behavior improves.

Keep notes on the symptoms you reproduced, the files you changed, and the tests you ran.

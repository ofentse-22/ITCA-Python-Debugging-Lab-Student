"""SQLite schema definition for the initial data model."""

from dataclasses import dataclass


LATEST_SCHEMA_VERSION = 1

UTC_TIMESTAMP_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


@dataclass(frozen=True)
class Migration:
    """A single ordered database migration."""

    version: int
    name: str
    statements: tuple[str, ...]


INITIAL_SCHEMA_STATEMENTS = (
    f"""
    CREATE TABLE students (
        student_id INTEGER PRIMARY KEY,
        student_number TEXT NOT NULL UNIQUE,
        first_name TEXT NOT NULL CHECK (length(trim(first_name)) > 0),
        last_name TEXT NOT NULL CHECK (length(trim(last_name)) > 0),
        email TEXT UNIQUE CHECK (email IS NULL OR length(trim(email)) > 0),
        phone TEXT,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'inactive', 'archived')),
        created_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        updated_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        archived_at TEXT
    )
    """,
    f"""
    CREATE TABLE courses (
        course_id INTEGER PRIMARY KEY,
        course_code TEXT NOT NULL UNIQUE,
        course_name TEXT NOT NULL CHECK (length(trim(course_name)) > 0),
        description TEXT,
        fee_amount TEXT NOT NULL DEFAULT '0'
            CHECK (length(trim(fee_amount)) > 0),
        status TEXT NOT NULL DEFAULT 'planned'
            CHECK (status IN ('planned', 'active', 'completed', 'archived')),
        created_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        updated_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL})
    )
    """,
    """
    CREATE TABLE modules (
        module_id INTEGER PRIMARY KEY,
        course_id INTEGER NOT NULL,
        module_code TEXT NOT NULL CHECK (length(trim(module_code)) > 0),
        module_name TEXT NOT NULL CHECK (length(trim(module_name)) > 0),
        sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'archived')),
        FOREIGN KEY (course_id)
            REFERENCES courses (course_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        UNIQUE (course_id, module_code),
        UNIQUE (course_id, sequence_number)
    )
    """,
    f"""
    CREATE TABLE trainers (
        trainer_id INTEGER PRIMARY KEY,
        trainer_number TEXT NOT NULL UNIQUE,
        first_name TEXT NOT NULL CHECK (length(trim(first_name)) > 0),
        last_name TEXT NOT NULL CHECK (length(trim(last_name)) > 0),
        email TEXT UNIQUE CHECK (email IS NULL OR length(trim(email)) > 0),
        phone TEXT,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'inactive', 'archived')),
        created_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        updated_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL})
    )
    """,
    f"""
    CREATE TABLE course_enrolments (
        enrolment_id INTEGER PRIMARY KEY,
        student_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        enrolment_date TEXT NOT NULL CHECK (length(trim(enrolment_date)) > 0),
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'completed', 'cancelled')),
        cancelled_at TEXT,
        cancellation_reason TEXT,
        created_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        updated_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        FOREIGN KEY (student_id)
            REFERENCES students (student_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        FOREIGN KEY (course_id)
            REFERENCES courses (course_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE trainer_assignments (
        assignment_id INTEGER PRIMARY KEY,
        trainer_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        assigned_from TEXT NOT NULL CHECK (length(trim(assigned_from)) > 0),
        assigned_to TEXT,
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'ended')),
        FOREIGN KEY (trainer_id)
            REFERENCES trainers (trainer_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        FOREIGN KEY (course_id)
            REFERENCES courses (course_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT
    )
    """,
    f"""
    CREATE TABLE attendance_sessions (
        session_id INTEGER PRIMARY KEY,
        course_id INTEGER NOT NULL,
        session_date TEXT NOT NULL CHECK (length(trim(session_date)) > 0),
        topic TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        FOREIGN KEY (course_id)
            REFERENCES courses (course_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        UNIQUE (course_id, session_date, topic)
    )
    """,
    f"""
    CREATE TABLE attendance_records (
        attendance_record_id INTEGER PRIMARY KEY,
        session_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'unknown'
            CHECK (status IN ('present', 'absent', 'late', 'excused', 'unknown')),
        notes TEXT,
        updated_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        FOREIGN KEY (session_id)
            REFERENCES attendance_sessions (session_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        FOREIGN KEY (student_id)
            REFERENCES students (student_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        UNIQUE (session_id, student_id)
    )
    """,
    f"""
    CREATE TABLE assessments (
        assessment_id INTEGER PRIMARY KEY,
        course_id INTEGER NOT NULL,
        module_id INTEGER,
        assessment_name TEXT NOT NULL CHECK (length(trim(assessment_name)) > 0),
        assessment_type TEXT NOT NULL
            CHECK (
                assessment_type IN ('practical', 'quiz', 'test', 'project', 'exam')
            ),
        max_mark TEXT NOT NULL CHECK (length(trim(max_mark)) > 0),
        weight TEXT CHECK (weight IS NULL OR length(trim(weight)) > 0),
        pass_mark TEXT CHECK (pass_mark IS NULL OR length(trim(pass_mark)) > 0),
        status TEXT NOT NULL DEFAULT 'active'
            CHECK (status IN ('active', 'archived')),
        created_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        updated_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        FOREIGN KEY (course_id)
            REFERENCES courses (course_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        FOREIGN KEY (module_id)
            REFERENCES modules (module_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT
    )
    """,
    f"""
    CREATE TABLE marks (
        mark_id INTEGER PRIMARY KEY,
        assessment_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        mark_obtained TEXT NOT NULL CHECK (length(trim(mark_obtained)) > 0),
        captured_at TEXT NOT NULL DEFAULT ({UTC_TIMESTAMP_SQL}),
        notes TEXT,
        FOREIGN KEY (assessment_id)
            REFERENCES assessments (assessment_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        FOREIGN KEY (student_id)
            REFERENCES students (student_id)
            ON UPDATE CASCADE
            ON DELETE RESTRICT,
        UNIQUE (assessment_id, student_id)
    )
    """,
    "CREATE INDEX idx_students_name ON students (last_name, first_name)",
    "CREATE INDEX idx_students_status ON students (status)",
    "CREATE INDEX idx_courses_status ON courses (status)",
    "CREATE INDEX idx_modules_course_id ON modules (course_id)",
    "CREATE INDEX idx_modules_status ON modules (status)",
    "CREATE INDEX idx_trainers_name ON trainers (last_name, first_name)",
    "CREATE INDEX idx_trainers_status ON trainers (status)",
    "CREATE INDEX idx_course_enrolments_student_id ON course_enrolments (student_id)",
    "CREATE INDEX idx_course_enrolments_course_id ON course_enrolments (course_id)",
    "CREATE INDEX idx_course_enrolments_status ON course_enrolments (status)",
    """
    CREATE UNIQUE INDEX uq_course_enrolments_active_student_course
    ON course_enrolments (student_id, course_id)
    WHERE status = 'active'
    """,
    "CREATE INDEX idx_trainer_assignments_trainer_id ON trainer_assignments (trainer_id)",
    "CREATE INDEX idx_trainer_assignments_course_id ON trainer_assignments (course_id)",
    "CREATE INDEX idx_trainer_assignments_status ON trainer_assignments (status)",
    """
    CREATE UNIQUE INDEX uq_trainer_assignments_active_trainer_course
    ON trainer_assignments (trainer_id, course_id)
    WHERE status = 'active'
    """,
    "CREATE INDEX idx_attendance_sessions_course_date ON attendance_sessions (course_id, session_date)",
    "CREATE INDEX idx_attendance_records_student_id ON attendance_records (student_id)",
    "CREATE INDEX idx_assessments_course_id ON assessments (course_id)",
    "CREATE INDEX idx_assessments_module_id ON assessments (module_id)",
    "CREATE INDEX idx_assessments_status ON assessments (status)",
    "CREATE INDEX idx_marks_student_id ON marks (student_id)",
)

MIGRATIONS = (
    Migration(
        version=1,
        name="initial_training_centre_schema",
        statements=INITIAL_SCHEMA_STATEMENTS,
    ),
)

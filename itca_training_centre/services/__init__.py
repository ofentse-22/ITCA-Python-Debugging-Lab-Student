"""Business service package with lazy public service exports."""

from importlib import import_module


_SERVICE_EXPORTS = {
    "AttendanceService": ".attendance_service",
    "CourseEnrolmentService": ".course_enrolment_service",
    "CourseService": ".course_service",
    "ImportExportService": ".import_export_service",
    "ModuleService": ".module_service",
    "StudentService": ".student_service",
    "TrainerAssignmentService": ".trainer_assignment_service",
}

__all__ = tuple(_SERVICE_EXPORTS)


def __getattr__(name: str):
    """Resolve public service exports without importing every service eagerly."""
    if name not in _SERVICE_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(_SERVICE_EXPORTS[name], __name__)
    if name == "CourseService":
        value = module
    else:
        value = getattr(module, f"{name}Workflow")
    globals()[name] = value
    return value

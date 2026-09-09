"""Course module domain model."""

from dataclasses import dataclass


MODULE_ACTIVE_STATUS = "active"
MODULE_ARCHIVED_STATUS = "archived"
MODULE_STATUSES = (MODULE_ACTIVE_STATUS, MODULE_ARCHIVED_STATUS)


@dataclass(frozen=True)
class Module:
    """A module/topic record belonging to a course."""

    module_id: int
    course_id: int
    module_code: str
    module_name: str
    sequence_number: int
    status: str

    @property
    def is_active(self) -> bool:
        """Return True when the module is currently active."""
        return self.status == MODULE_ACTIVE_STATUS

    @property
    def is_archived(self) -> bool:
        """Return True when the module is archived."""
        return self.status == MODULE_ARCHIVED_STATUS

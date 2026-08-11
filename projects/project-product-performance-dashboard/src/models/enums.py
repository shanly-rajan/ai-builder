"""Canonical categorical values used by the dashboard data model."""

from enum import StrEnum


class StringEnum(StrEnum):
    """Base enum whose members serialize to their human-readable values."""

    def __str__(self) -> str:
        """Return the serialized value."""
        return self.value


class ProjectStatus(StringEnum):
    """Delivery lifecycle states for a project."""

    PLANNING = "Planning"
    IN_PROGRESS = "In Progress"
    TESTING = "Testing"
    COMPLETE = "Complete"
    CANCELLED = "Cancelled"


class TestStatus(StringEnum):
    """Mutually exclusive test execution outcomes."""

    PASSED = "Passed"
    FAILED = "Failed"
    BLOCKED = "Blocked"
    NOT_RUN = "Not Run"


class TestCategory(StringEnum):
    """Supported project test categories."""

    UNIT = "Unit"
    INTEGRATION = "Integration"
    SYSTEM = "System"
    REGRESSION = "Regression"
    PERFORMANCE = "Performance"
    SECURITY = "Security"
    UAT = "UAT"
    PRODUCTION_VALIDATION = "Production Validation"


class DefectSeverity(StringEnum):
    """Defect severity levels in descending order."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class DefectStatus(StringEnum):
    """Defect workflow states."""

    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    RESOLVED = "Resolved"


class UATStatus(StringEnum):
    """User-acceptance-test assessment states."""

    NOT_APPLICABLE = "Not Applicable"
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    PASSED = "Passed"
    FAILED = "Failed"


class ProductLifecycleStatus(StringEnum):
    """Commercial lifecycle states for a product."""

    PILOT = "Pilot"
    ACTIVE = "Active"
    SUNSET = "Sunset"


class ProjectCostCategory(StringEnum):
    """Non-resource engineering cost categories."""

    ENGINEERING_INFRASTRUCTURE = "Engineering Infrastructure"
    EXTERNAL_ENGINEERING = "External Engineering/Integration"


class ProductInvestmentType(StringEnum):
    """Non-engineering product investment categories."""

    ADDITIONAL_LAUNCH_COST = "Additional Launch Cost"
    THIRD_PARTY_SETUP_COST = "Third-party Setup Cost"


def enum_values(enum_type: type[StringEnum]) -> frozenset[str]:
    """Return the allowed serialized values for an enum.

    Args:
        enum_type: Enum class whose values should be returned.

    Returns:
        Immutable set of serialized enum values.
    """
    return frozenset(member.value for member in enum_type)

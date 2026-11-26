"""服務層統一回傳格式與 F5/F7 使用的錯誤代碼。"""
from dataclasses import dataclass, field

Slot = tuple[int, int]

NOT_FOUND = "NOT_FOUND"
INVALID_VALUE = "INVALID_VALUE"
INVALID_SLOT = "INVALID_SLOT"
COURSE_FULL = "COURSE_FULL"
COURSE_CANCELLED = "COURSE_CANCELLED"
FORBIDDEN_SLOT = "FORBIDDEN_SLOT"
REQUIRED_EXCLUDED = "REQUIRED_EXCLUDED"
REQUIRED_CONFLICT = "REQUIRED_CONFLICT"
CREDIT_RANGE_INVALID = "CREDIT_RANGE_INVALID"
REQUIRED_EXCEEDS_MAX = "REQUIRED_EXCEEDS_MAX"
MIN_CREDITS_UNREACHABLE = "MIN_CREDITS_UNREACHABLE"
STUDENT_TIME_CONFLICT = "STUDENT_TIME_CONFLICT"
ACTIVITY_TIME_CONFLICT = "ACTIVITY_TIME_CONFLICT"
NO_FEASIBLE_TIMETABLE = "NO_FEASIBLE_TIMETABLE"


@dataclass
class ErrorItem:
    code: str
    message: str
    slots: list[Slot] = field(default_factory=list)
    related_id: str | None = None


@dataclass
class Result:
    ok: bool
    data: object = None
    errors: list[ErrorItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

"""F5 使用的規格 v1 資料類別；不儲存衍生人數與學生報名名單。"""
from dataclasses import dataclass, field

from .result import ErrorItem, Slot


@dataclass
class Course:
    code: str
    name: str
    credits: int
    type: str
    teacher: str
    capacity: int
    room_id: str
    slots: list[str]
    status: str = "open"


@dataclass
class Student:
    student_id: str
    name: str
    dept_year: str
    credit_limit: int = 25
    enrolled_courses: list[str] = field(default_factory=list)


@dataclass
class Activity:
    activity_id: str
    name: str
    date: str
    start_time: str
    end_time: str
    recurrence: str = "once"
    room_id: str | None = None
    participants: list[str] = field(default_factory=list)
    status: str = "scheduled"
    # 僅供舊資料轉接或載入後快取；不是規格 JSON 的儲存欄位。
    slots: list[str] = field(default_factory=list, repr=False)


@dataclass
class SystemData:
    courses: dict[str, Course] = field(default_factory=dict)
    students: dict[str, Student] = field(default_factory=dict)
    classrooms: dict[str, dict] = field(default_factory=dict)
    activities: dict[str, Activity] = field(default_factory=dict)
    enrollment_log: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Occupancy:
    source_type: str
    source_id: str
    name: str
    slots: frozenset[Slot]
    date: str | None = None
    room_id: str | None = None


@dataclass
class FilterCriteria:
    desired_courses: list[str] = field(default_factory=list)
    required_courses: list[str] = field(default_factory=list)
    min_credits: int = 0
    max_credits: int = 25
    forbidden_slots: list[str] = field(default_factory=list)
    preferred_days: list[int] = field(default_factory=list)


@dataclass
class CourseOption:
    code: str
    name: str
    credits: int = 0
    required: bool = False
    preferred: bool = True
    slots: list[Slot] = field(default_factory=list)
    reasons: list[ErrorItem] = field(default_factory=list)


@dataclass
class FilterReport:
    student_id: str
    student_name: str
    criteria: FilterCriteria
    candidates: list[CourseOption] = field(default_factory=list)
    excluded: list[CourseOption] = field(default_factory=list)
    already_enrolled: list[str] = field(default_factory=list)
    current_credits: int = 0
    required_credits: int = 0
    available_credits: int = 0
    feasible: bool = False

"""規格 v1 資料與 F5/F7 規劃結果；不儲存衍生人數與學生報名名單。"""
from dataclasses import asdict, dataclass, field, is_dataclass

from .result import ErrorItem, Slot


class RecordMixin:
    """資料類別相容舊版 record['field']，比較時忽略非儲存快取。"""
    _transient_fields = ()

    def __getitem__(self, key):
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def __setitem__(self, key, value):
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __eq__(self, other):
        if isinstance(other, dict):
            record = dict(other)
        elif is_dataclass(other) and not isinstance(other, type):
            record = asdict(other)
        else:
            return NotImplemented
        current = asdict(self)
        for key in self._transient_fields:
            current.pop(key, None)
            record.pop(key, None)
        return current == record


@dataclass(eq=False)
class Course(RecordMixin):
    code: str
    name: str
    credits: int
    type: str
    teacher: str
    capacity: int
    room_id: str
    slots: list[str]
    status: str = "open"


@dataclass(eq=False)
class Student(RecordMixin):
    student_id: str
    name: str
    dept_year: str
    credit_limit: int = 25
    enrolled_courses: list[str] = field(default_factory=list)


@dataclass(eq=False)
class Activity(RecordMixin):
    _transient_fields = ("slots",)
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
    activity_type: str = "other"
    expected_attendees: int = 20
    required_equipment: list[str] = field(default_factory=list)
    organizer: str = "未指定"


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


@dataclass(frozen=True)
class ScoreWeights:
    """F7 軟性偏好的非負權重；總分愈高愈好。"""
    days: float = 5
    gaps: float = 2
    early: float = 3
    span: float = 1
    preferred_courses: float = 10
    preferred_days: float = 5


@dataclass(frozen=True)
class ScheduleScore:
    days: int
    gaps: int
    early: int
    span: int
    preferred_course_ratio: float
    preferred_day_ratio: float
    total: float


@dataclass
class ScheduleOption:
    course_codes: list[str]
    added_courses: list[str]
    total_credits: int
    score: ScheduleScore
    occupancies: list[Occupancy] = field(default_factory=list)


@dataclass
class OptimizerReport:
    student_id: str
    student_name: str
    filter_report: FilterReport
    weights: ScoreWeights
    preferred_courses: list[str]
    top_k: int | None
    schedules: list[ScheduleOption] = field(default_factory=list)
    feasible_count: int = 0
    visited_nodes: int = 0

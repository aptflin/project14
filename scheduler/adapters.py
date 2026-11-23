"""將現有 camelCase 與 schema_version=1 records 轉為同一份 SystemData；不寫檔。"""
from dataclasses import asdict

from .models import Activity, Course, Student, SystemData


def _records(value: list | dict) -> list:
    if isinstance(value, dict):
        if value.get("schema_version") != 1 or not isinstance(value.get("records"), list):
            raise ValueError("資料須為 schema_version=1 且 records 為清單")
        value = value["records"]
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("資料須為物件清單")
    return value


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("代號須為非空字串")
    return value.strip().upper()


def _identifiers(value: list) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("代號清單格式不合法")
    return list(dict.fromkeys(_identifier(item) for item in value))


def _slots(item: dict) -> list[str]:
    if "slots" in item:
        if not isinstance(item["slots"], list):
            raise ValueError("slots 須為清單")
        return list(item["slots"])
    schedules = item.get("schedules", [])
    if not isinstance(schedules, list) or not all(isinstance(slot, dict) for slot in schedules):
        raise ValueError("schedules 須為時段物件清單")
    return [f"{slot['day']}-{str(slot['period']).lower()}" for slot in schedules]


def _insert(index: dict, key: str, value: object) -> None:
    if key in index:
        raise ValueError(f"資料代號重複：{key}")
    index[key] = value


def _courses(records: list) -> dict[str, Course]:
    courses = {}
    for item in records:
        key = _identifier(item.get("code", item.get("courseId")))
        course = Course(key, item["name"], item["credits"],
                        item.get("type", "required" if item.get("isRequired") else "elective"),
                        item.get("teacher", ""), item.get("capacity", item.get("maxStudents")),
                        item.get("room_id", item.get("roomId", "")), _slots(item), item.get("status", "open"))
        if type(course.credits) is not int or not 1 <= course.credits <= 6:
            raise ValueError(f"{key} 學分須為 1–6 的整數")
        if type(course.capacity) is not int or course.capacity < 1:
            raise ValueError(f"{key} 人數上限須為正整數")
        if course.status not in ("open", "cancelled"):
            raise ValueError(f"{key} 課程狀態不合法")
        _insert(courses, key, course)
    return courses


def _students(records: list) -> dict[str, Student]:
    students = {}
    for item in records:
        key = _identifier(item.get("student_id", item.get("studentId")))
        limit = item.get("credit_limit", item.get("maxCredits", 25))
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError(f"{key} 學分上限須為 1–30 的整數")
        student = Student(key, item.get("name", ""), item.get("dept_year", item.get("department", "")),
                          limit, _identifiers(item.get("enrolled_courses", item.get("enrolledCourses", []))))
        _insert(students, key, student)
    return students


def _activities(records: list, student_records: list) -> dict[str, Activity]:
    activities = {}
    for item in records:
        key = _identifier(item.get("activity_id", item.get("activityId")))
        participants = _identifiers(item.get("participants", []))
        for student in student_records:
            if key in _identifiers(student.get("enrolledActivities", [])):
                participants.append(_identifier(student.get("student_id", student.get("studentId"))))
        activity = Activity(key, item["name"], item.get("date", ""),
                            item.get("start_time", item.get("startTime", "")),
                            item.get("end_time", item.get("endTime", "")), item.get("recurrence", "weekly"),
                            item.get("room_id", item.get("roomId")), list(dict.fromkeys(participants)),
                            item.get("status", "scheduled"), _slots(item))
        activity.activity_type = item.get("activity_type", item.get("activityType", "other"))
        activity.expected_attendees = item.get("expected_attendees", item.get("expectedAttendees", 20))
        activity.required_equipment = list(item.get("required_equipment", item.get("requiredEquipment", [])))
        activity.organizer = item.get("organizer", "未指定")
        if activity.recurrence not in ("once", "weekly") or activity.status not in ("scheduled", "cancelled"):
            raise ValueError(f"{key} 活動狀態或重複方式不合法")
        _insert(activities, key, activity)
    return activities


def system_data_from_records(courses: list | dict, students: list | dict,
                             activities: list | dict, classrooms: list | dict) -> SystemData:
    """接收舊清單或 v1 records 包裝，回傳獨立 SystemData；格式錯誤拋出 ValueError。"""
    course_records, student_records = _records(courses), _records(students)
    rooms = _records(classrooms)
    data = SystemData(_courses(course_records), _students(student_records),
                      {_identifier(room.get("room_id", room.get("roomId"))): dict(room) for room in rooms},
                      _activities(_records(activities), student_records))
    for student in data.students.values():
        if any(code not in data.courses for code in student.enrolled_courses):
            raise ValueError(f"{student.student_id} 已選課程參照不存在")
    activity_ids = set(data.activities)
    for student in student_records:
        if set(_identifiers(student.get("enrolledActivities", []))) - activity_ids:
            raise ValueError("學生已報名活動參照不存在")
    return data


def normalise_data(data: SystemData) -> SystemData:
    """複製並正規化 SystemData 中的代號；不修改呼叫者的資料。"""
    def record(item):
        return dict(item) if isinstance(item, dict) else asdict(item)

    return system_data_from_records([record(item) for item in data.courses.values()],
                                    [record(item) for item in data.students.values()],
                                    [record(item) for item in data.activities.values()], [])

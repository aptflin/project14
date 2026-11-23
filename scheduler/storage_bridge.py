"""v1 儲存資料與現有 F1–F5 服務之間的純記憶體轉接，不讀寫檔案。"""
from copy import deepcopy
from dataclasses import asdict
from datetime import date

from .models import SystemData
from .timeslot import format_slot, parse_slot, time_range_to_slots


def record_dict(value: object) -> dict:
    """複製 dict 或資料類別，回傳可供轉接的獨立紀錄。"""
    return deepcopy(value) if isinstance(value, dict) else asdict(value)


def legacy_views(data: SystemData) -> dict[str, list]:
    """產生 camelCase 視圖；活動參加者以 participants 為單一資料來源。"""
    courses, students, classrooms, activities = [], [], [], []
    for value in data.courses.values():
        c = record_dict(value)
        courses.append({"courseId": c["code"], "name": c["name"], "credits": c["credits"],
                        "isRequired": c["type"] == "required", "teacher": c["teacher"],
                        "maxStudents": c["capacity"], "roomId": c["room_id"], "status": c["status"],
                        "schedules": [_legacy_slot(parse_slot(slot)) for slot in c["slots"]]})
    activity_records = [record_dict(value) for value in data.activities.values()]
    for value in data.students.values():
        s = record_dict(value)
        students.append({"studentId": s["student_id"], "name": s["name"], "department": s["dept_year"],
                         "maxCredits": s["credit_limit"], "enrolledCourses": s["enrolled_courses"],
                         "enrolledActivities": [a["activity_id"] for a in activity_records
                                                if a["status"] != "cancelled" and s["student_id"] in a["participants"]]})
    for value in data.classrooms.values():
        r = record_dict(value)
        classrooms.append(dict(r, roomId=r["room_id"],
                               unavailableSlots=[_legacy_slot(parse_slot(slot)) for slot in r["unavailable_slots"]]))
    for a in activity_records:
        slots = time_range_to_slots(date.fromisoformat(a["date"]).isoweekday(), a["start_time"], a["end_time"])
        activities.append({"activityId": a["activity_id"], "name": a["name"], "activityType": a["activity_type"],
                           "date": a["date"], "startTime": a["start_time"], "endTime": a["end_time"],
                           "recurrence": a["recurrence"], "expectedAttendees": a["expected_attendees"],
                           "requiredEquipment": a["required_equipment"], "organizer": a["organizer"],
                           "roomId": a["room_id"], "status": a["status"],
                           "schedules": [_legacy_slot(slot) for slot in slots]})
    return {"courses": courses, "students": students, "classrooms": classrooms, "activities": activities}


def _legacy_slot(slot: tuple[int, int]) -> dict:
    return {"day": slot[0], "period": format_slot(slot).split("-")[1]}


def update_from_views(original: SystemData, views: dict[str, list]) -> SystemData:
    """將已驗證的服務結果轉回 v1 資料，保留選課歷程且不改動 original。"""
    result = deepcopy(original)
    result.courses = {c["courseId"]: {
        "code": c["courseId"], "name": c["name"], "credits": c["credits"],
        "type": "required" if c["isRequired"] else "elective", "teacher": c["teacher"],
        "capacity": c["maxStudents"], "room_id": c["roomId"], "status": c.get("status", "open"),
        "slots": [f"{slot['day']}-{slot['period']}" for slot in c["schedules"]],
    } for c in views["courses"]}
    result.students = {s["studentId"]: {
        "student_id": s["studentId"], "name": s["name"], "dept_year": s["department"],
        "credit_limit": s["maxCredits"], "enrolled_courses": list(s["enrolledCourses"]),
    } for s in views["students"]}
    result.activities = {a["activityId"]: {
        "activity_id": a["activityId"], "name": a["name"], "activity_type": a["activityType"],
        "date": a["date"], "start_time": a["startTime"], "end_time": a["endTime"],
        "recurrence": a["recurrence"], "expected_attendees": a["expectedAttendees"],
        "required_equipment": list(a["requiredEquipment"]), "room_id": a["roomId"],
        "participants": [s["studentId"] for s in views["students"] if a["activityId"] in s["enrolledActivities"]],
        "organizer": a["organizer"], "status": a["status"],
    } for a in views["activities"]}
    return result

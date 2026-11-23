"""可重現的 v1 示範資料；純記憶體產生，不覆寫正式資料。"""
from .models import SystemData


def create_sample_data() -> SystemData:
    """建立 20 門課、15 名學生、5 間教室、10 項活動及選課紀錄。"""
    data = SystemData()
    rooms = [("EE-101", 60), ("EE-201", 40), ("LIB-101", 30), ("ADM-301", 100), ("SCI-201", 50)]
    for room_id, capacity in rooms:
        data.classrooms[room_id] = {
            "room_id": room_id, "name": f"{room_id} 教室", "building": room_id.split("-")[0],
            "capacity": capacity, "equipment": ["projector", "whiteboard"],
            "unavailable_slots": [], "status": "active",
        }
    for index in range(20):
        code = f"CS{101 + index}"
        data.courses[code] = {
            "code": code, "name": f"示範課程 {index + 1}", "credits": index % 4 + 1,
            "type": "required" if index < 8 else "elective", "teacher": f"教師 {index % 5 + 1}",
            "capacity": 10, "room_id": rooms[index % 5][0],
            "slots": [f"{index // 4 + 1}-{index % 4 + 1}"], "status": "open",
        }
    for index in range(1, 16):
        sid = f"S{index:03d}"
        data.students[sid] = {"student_id": sid, "name": f"學生 {index:02d}",
                              "dept_year": "資工二", "credit_limit": 25, "enrolled_courses": []}
    for index in range(1, 11):
        aid = f"EV{index:03d}"
        data.activities[aid] = {
            "activity_id": aid, "name": f"校園活動 {index}", "activity_type": "study_group",
            "date": f"2026-11-{index:02d}", "start_time": "18:10", "end_time": "19:00",
            "recurrence": "once", "expected_attendees": 10, "required_equipment": [],
            "room_id": rooms[index % 5][0], "participants": [], "organizer": "學會", "status": "scheduled",
        }
    return data

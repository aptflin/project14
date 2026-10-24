import unittest

from f4_system import (
    timeToSchedules, prepareActivity, findSuitableRooms, addActivity, updateActivity,
    cancelActivity, queryActivities, registerActivity, formatActivity, formatAllocation,
)


def course(cid, slots, room):
    return {
        "courseId": cid, "name": cid, "credits": 3, "maxStudents": 50, "roomId": room,
        "schedules": [{"day": day, "period": period} for day, period in slots],
    }


def activityData(aid, date="2026-10-15", start="13:30", end="15:30", people=30, **extra):

    data = {
        "activityId": aid, "name": f"活動{aid}", "activityType": "lecture",
        "date": date, "startTime": start, "endTime": end, "recurrence": "once",
        "expectedAttendees": people, "requiredEquipment": [], "organizer": "資工系學會",
    }
    data.update(extra)
    return data


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [
            {"roomId": "EE-101", "capacity": 60, "equipment": ["projector", "whiteboard"]},
            {"roomId": "LIB-101", "capacity": 30, "equipment": ["whiteboard"]},
            {"roomId": "ADM-301", "capacity": 100, "equipment": ["projector", "microphone", "speaker"]},
            {"roomId": "SCI-201", "capacity": 50, "equipment": ["projector"]},
        ]
        self.courses = [course("PE101", [(4, "6"), (4, "7")], "SCI-201")]
        self.activities = []
        self.students = [
            {"studentId": f"S{i:03d}", "name": f"學生{i}", "maxCredits": 25, "enrolledCourses": []}
            for i in range(1, 7)
        ]

    def add(self, data):
        return addActivity(data, self.activities, self.courses, self.rooms)

    def register(self, sid, aid):
        return registerActivity(sid, aid, self.courses, self.students, self.activities, self.rooms)

    def prepared(self, data):
        activity, errors = prepareActivity(data, self.activities)
        self.assertEqual(errors, [])
        return activity

    def test_1330_to_1530_maps_to_periods_6_7_8(self):
        schedules, errors = timeToSchedules("2026-10-15", "13:30", "15:30")
        self.assertEqual(errors, [])
        self.assertEqual(schedules, [{"day": 4, "period": p} for p in ("6", "7", "8")])

    def test_time_outside_0810_2000_or_reversed_is_rejected(self):
        self.assertTrue(timeToSchedules("2026-10-15", "07:00", "09:00")[1][0].startswith("[INVALID_TIME_RANGE]"))
        self.assertTrue(timeToSchedules("2026-10-15", "19:00", "20:30")[1][0].startswith("[INVALID_TIME_RANGE]"))
        self.assertTrue(timeToSchedules("2026-10-15", "15:00", "13:00")[1][0].startswith("[INVALID_TIME_RANGE]"))
        self.assertTrue(timeToSchedules("2026-02-30", "13:00", "14:00")[1][0].startswith("[INVALID_DATE]"))

    def test_all_field_errors_listed_at_once(self):
        ok, errors, _ = self.add(activityData(
            "X1", people=0, activityType="party", recurrence="daily",
            requiredEquipment=["laser"], start="15:00", end="13:00",
        ))
        self.assertFalse(ok)
        codes = [e.split("]")[0] + "]" for e in errors]
        for code in ("[INVALID_ID_FORMAT]", "[INVALID_CAPACITY]", "[INVALID_VALUE]", "[INVALID_TIME_RANGE]"):
            self.assertIn(code, codes)

    def test_suitable_rooms_smallest_first_and_course_room_conflict(self):
        activity = self.prepared(activityData("EV001", people=30, requiredEquipment=["projector"]))
        suitable, unmet = findSuitableRooms(activity, self.courses, self.activities, self.rooms)
        self.assertEqual(suitable, ["EE-101", "ADM-301"])
        self.assertIn(("EQUIPMENT_MISSING", "缺少設備：projector"), unmet["LIB-101"])
        self.assertIn(("ROOM_TIME_CONFLICT", "時段衝突：星期四第 6、7 節已有課程 PE101 PE101"),
                      unmet["SCI-201"])

    def test_no_room_lists_every_unmet_condition(self):
        activity = self.prepared(activityData("EV006", people=200, requiredEquipment=["microphone"]))
        suitable, unmet = findSuitableRooms(activity, self.courses, self.activities, self.rooms)
        self.assertEqual(suitable, [])
        text = formatAllocation(activity, self.rooms, unmet)
        self.assertIn("配置結果：失敗，無合適教室", text)
        self.assertIn("LIB-101 容量不足（需 200，教室 30）；缺少設備：microphone", text)
        self.assertIn("ADM-301 容量不足（需 200，教室 100）", text)

    def test_disabled_room_and_unavailable_slots(self):
        self.rooms[0]["status"] = "disabled"
        self.rooms[2]["unavailableSlots"] = [{"day": 4, "period": "8"}]
        activity = self.prepared(activityData("EV001"))
        _, unmet = findSuitableRooms(activity, self.courses, self.activities, self.rooms)
        self.assertIn(("ROOM_UNAVAILABLE", "教室停用"), unmet["EE-101"])
        self.assertIn(("ROOM_UNAVAILABLE", "教室停用時段：星期四第 8 節"), unmet["ADM-301"])

    def test_no_suitable_room_can_still_create_unassigned(self):
        ok, messages, _ = self.add(activityData("EV006", people=200))
        self.assertTrue(ok)
        self.assertIsNone(self.activities[0]["roomId"])
        self.assertIn("尚未配置教室", messages[0])

    def test_two_once_activities_same_weekday_different_date_do_not_conflict(self):
        self.assertTrue(self.add(activityData("EV001", roomId="EE-101"))[0])
        self.assertTrue(self.add(activityData("EV002", date="2026-10-22", roomId="EE-101"))[0])

    def test_weekly_and_once_activity_same_slot_conflict(self):
        self.assertTrue(self.add(activityData("EV001", recurrence="weekly", roomId="EE-101"))[0])
        ok, messages, unmet = self.add(activityData("EV002", date="2026-10-22", roomId="EE-101"))
        self.assertFalse(ok)
        self.assertTrue(messages[0].startswith("[NO_SUITABLE_ROOM]"))
        self.assertIn("EV001", unmet["EE-101"][0][1])


    def test_ten_activities_full_registration_and_cancel(self):
        for i in range(1, 9):
            day = 6 + 7 * (i - 1)
            date = f"2026-{10 + (day - 1) // 31:02d}-{(day - 1) % 31 + 1:02d}"
            ok, messages, _ = self.add(activityData(
                f"EV{i:03d}", date=date, start="18:10", end="19:00", people=3, roomId="LIB-101",
            ))
            self.assertTrue(ok, messages)
        self.assertTrue(self.add(activityData("EV009", people=500))[0])
        self.assertTrue(self.add(activityData("EV010", recurrence="weekly", start="08:10",
                                              end="09:00", roomId="EE-101"))[0])
        self.assertEqual(len(self.activities), 10)

        for sid in ("S001", "S002", "S003"):
            self.assertTrue(self.register(sid, "EV001")["success"])
        full = self.register("S004", "EV001")
        self.assertFalse(full["success"])
        self.assertIn("[ACTIVITY_FULL] 活動報名額滿：3/3 人", full["errors"])

        again = self.register("S001", "EV001")
        self.assertTrue(any("已參加此活動" in e for e in again["errors"]))

        self.assertTrue(self.register("S001", "EV002")["success"])

        ok, _, affected = cancelActivity("EV001", self.activities, self.students)
        self.assertTrue(ok)
        self.assertEqual(affected, ["S001", "S002", "S003"])
        self.assertEqual(self.students[0]["enrolledActivities"], ["EV002"])
        self.assertEqual(queryActivities(self.activities, qStatus="cancelled")[0]["activityId"], "EV001")

        cancelled = self.register("S004", "EV001")
        self.assertIn("[ACTIVITY_CANCELLED] 活動 EV001 已取消", cancelled["errors"])

        self.assertTrue(self.add(activityData("EV011", date="2026-10-06", start="18:10",
                                              end="19:00", people=3, roomId="LIB-101"))[0])

    def test_registration_conflicts_with_enrolled_course(self):
        self.students[0]["enrolledCourses"] = ["PE101"]
        self.add(activityData("EV001", roomId="EE-101"))
        result = self.register("S001", "EV001")
        self.assertFalse(result["success"])
        self.assertEqual([(c["period"], c["otherId"]) for c in result["conflicts"]],
                         [("6", "PE101"), ("7", "PE101")])

    def test_registration_limit_is_min_of_expected_and_room_capacity(self):
        self.add(activityData("EV001", people=2, roomId="LIB-101"))
        self.activities[0]["expectedAttendees"] = 50
        for student in self.students:
            student["enrolledActivities"] = ["EV001"]
        self.students.append({"studentId": "S100", "maxCredits": 25, "enrolledCourses": []})
        self.students.extend({"studentId": f"T{i}", "maxCredits": 25, "enrolledActivities": ["EV001"]}
                             for i in range(24))
        result = self.register("S100", "EV001")
        self.assertIn("[ACTIVITY_FULL] 活動報名額滿：30/30 人", result["errors"])

    def test_update_rechecks_room_and_registered_count(self):
        self.add(activityData("EV001", roomId="EE-101"))
        self.add(activityData("EV002", start="08:10", end="09:00", roomId="EE-101"))
        ok, _, unmet = updateActivity("EV002", {"startTime": "14:00"}, self.activities,
                                      self.courses, self.rooms, self.students)
        self.assertFalse(ok) 
        ok, _, unmet = updateActivity("EV002", {"startTime": "14:10", "endTime": "15:00"},
                                      self.activities, self.courses, self.rooms, self.students)
        self.assertFalse(ok)
        self.assertIn("EV001", unmet["EE-101"][0][1])

        self.students[0]["enrolledActivities"] = ["EV001"]
        self.students[1]["enrolledActivities"] = ["EV001"]
        ok, messages, _ = updateActivity("EV001", {"expectedAttendees": 1}, self.activities,
                                         self.courses, self.rooms, self.students)
        self.assertFalse(ok)
        self.assertTrue(messages[0].startswith("[CAPACITY_BELOW_ENROLLED]"))

        ok, _, _ = updateActivity("ev001", {"name": "新名稱"}, self.activities,
                                  self.courses, self.rooms, self.students)
        self.assertTrue(ok)
        self.assertEqual(self.activities[0]["name"], "新名稱")

    def test_duplicate_id_is_case_insensitive(self):
        self.assertTrue(self.add(activityData("EV001"))[0])
        ok, messages, _ = self.add(activityData("ev001"))
        self.assertFalse(ok)
        self.assertIn("[DUPLICATE_ID] 活動代號 EV001 已存在", messages)

    def test_query_by_date_type_room_status(self):
        self.add(activityData("EV001", roomId="EE-101"))
        self.add(activityData("EV002", date="2026-10-16", activityType="club", roomId="EE-101"))
        self.assertEqual(len(queryActivities(self.activities, qDate="2026-10-16")), 1)
        self.assertEqual(len(queryActivities(self.activities, qType="lecture")), 1)
        self.assertEqual(len(queryActivities(self.activities, qRoom="ee-101")), 2)
        self.assertEqual(len(queryActivities(self.activities, qStatus="scheduled")), 2)

    def test_display_format(self):
        activity = self.prepared(activityData("EV005", people=80, requiredEquipment=["projector", "microphone"]))
        self.assertEqual(formatActivity(activity).splitlines(), [
            "活動：EV005 活動EV005（2026-10-15 星期四 13:30–15:30，對應第 6、7、8 節）",
            "需求：80 人、projector、microphone",
        ])
        suitable, unmet = findSuitableRooms(activity, self.courses, self.activities, self.rooms)
        self.assertEqual(suitable, ["ADM-301"])
        activity["roomId"] = suitable[0]
        self.assertEqual(formatAllocation(activity, self.rooms, {}), "配置結果：成功 → ADM-301（容量 100）")


if __name__ == "__main__":
    unittest.main()

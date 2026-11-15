"""以獨立資料驗證 F1 → F2 → F3 與 F4 → F3 的完整流程。"""
import unittest

from f1_system import addCourse
from f2_system import enrollCourse
from f3_system import buildTimetable, findFreeBlocks, queryTimetable, summarizeTimetable
from f4_system import addActivity, cancelActivity, registerActivity


class FeatureIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [{"roomId": "R101", "capacity": 30, "equipment": []}]
        self.courses, self.activities = [], []
        self.students = [{"studentId": "S001", "name": "測試學生", "maxCredits": 6, "enrolledCourses": []}]

    def test_add_enroll_then_build_timetable_and_free_blocks(self):
        course = {
            "courseId": "CS101", "name": "Python", "credits": 3,
            "isRequired": True, "teacher": "王老師", "maxStudents": 30,
            "roomId": "R101", "schedules": [{"day": 1, "period": "1"}, {"day": 1, "period": "3"}],
        }
        self.assertTrue(addCourse(course, self.courses, self.rooms)[0])
        result = enrollCourse("S001", "CS101", self.courses, self.students, self.activities, self.rooms)
        self.assertTrue(result["success"], result)
        timetable, errors = buildTimetable("S001", self.courses, self.students, self.activities)
        self.assertEqual(errors, [])
        self.assertEqual([(day, period) for day, period, _ in queryTimetable(timetable)], [(1, "1"), (1, "3")])
        summary = summarizeTimetable(timetable, "S001", self.courses, self.students)
        self.assertEqual((summary["totalCredits"], summary["totalPeriods"], summary["totalGaps"]), (3, 2, 1))
        blocks, errors = findFreeBlocks(timetable, 1, 1, "1", "3", 1)
        self.assertEqual(errors, [])
        self.assertEqual(blocks, [{"day": 1, "startPeriod": "2", "endPeriod": "2", "length": 1}])

    def test_create_register_cancel_activity_updates_timetable(self):
        data = {
            "activityId": "EV001", "name": "讀書會", "activityType": "study_group",
            "date": "2026-10-26", "startTime": "08:10", "endTime": "09:00",
            "recurrence": "once", "expectedAttendees": 10, "requiredEquipment": [],
            "organizer": "測試主辦人", "roomId": "R101",
        }
        self.assertTrue(addActivity(data, self.activities, self.courses, self.rooms)[0])
        result = registerActivity("S001", "EV001", self.courses, self.students, self.activities, self.rooms)
        self.assertTrue(result["success"], result)
        timetable, errors = buildTimetable("S001", self.courses, self.students, self.activities)
        self.assertEqual(errors, [])
        self.assertEqual(len(queryTimetable(timetable, itemId="EV001")), 1)
        self.assertEqual(summarizeTimetable(timetable, "S001", self.courses, self.students)["totalCredits"], 0)
        ok, _, affected = cancelActivity("EV001", self.activities, self.students)
        self.assertTrue(ok)
        self.assertEqual(affected, ["S001"])
        timetable, errors = buildTimetable("S001", self.courses, self.students, self.activities)
        self.assertEqual(errors, [])
        self.assertEqual(queryTimetable(timetable), [])


if __name__ == "__main__":
    unittest.main()

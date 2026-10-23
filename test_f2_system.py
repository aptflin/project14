import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from f2_system import (
    checkEnrollment, enrollCourse, checkActivityParticipation, joinActivity,
    checkClassroomConflicts, formatResult,
)


def course(cid, slots, room="R101", credits=3, limit=20):
    return {
        "courseId": cid, "name": cid, "credits": credits,
        "maxStudents": limit, "roomId": room,
        "schedules": [{"day": day, "period": period} for day, period in slots],
    }


def activity(aid, slots, room="R102"):
    item = course(aid, slots, room)
    item["activityId"] = item.pop("courseId")
    return item


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.courses = [course("CS102", [(4, "5"), (2, "4"), (2, "3")]),
                        course("MA101", [(2, "3"), (2, "4")], "R103")]
        self.students = [{"studentId": "S001", "maxCredits": 24,
                          "enrolledCourses": ["MA101"], "enrolledActivities": ["A001"]}]
        self.activities = [activity("A001", [(4, "5")])]
        self.rooms = [{"roomId": f"R10{i}"} for i in range(1, 5)]

    def check(self):
        return checkEnrollment("S001", "CS102", self.courses, self.students,
                               self.activities, self.rooms)

    def test_collects_every_student_conflict_sorted(self):
        result = self.check()
        self.assertFalse(result["success"])
        self.assertEqual([(c["day"], c["period"], c["otherId"]) for c in result["conflicts"]],
                         [(2, "3", "MA101"), (2, "4", "MA101"), (4, "5", "A001")])
        output = formatResult(result)
        self.assertIn("已參加活動：A001", output)
        self.assertIn("加選後學分：6", output)

    def test_all_limits_and_room_conflicts_are_independent(self):
        self.students[0]["maxCredits"] = 3
        self.courses[0]["maxStudents"] = 1
        self.students.append({"studentId": "S002", "enrolledCourses": ["CS102"]})
        self.courses.append(course("OTHER", [(2, "3")]))
        self.activities.append(activity("A002", [(4, "5")], "R101"))
        result = self.check()
        self.assertEqual(len(result["conflicts"]), 5)
        self.assertTrue(any("學分超過" in e for e in result["errors"]))
        self.assertTrue(any("額滿" in e for e in result["errors"]))

    def test_full_course_rejected_without_any_time_conflict(self):
        self.students[0]["enrolledCourses"] = []
        self.students[0]["enrolledActivities"] = []
        self.courses[0]["maxStudents"] = 1
        self.students.append({"studentId": "S002", "enrolledCourses": ["CS102"]})
        result = self.check()
        self.assertFalse(result["success"])
        self.assertEqual(result["conflicts"], [])
        self.assertIn("課程已額滿", result["errors"][0])

    def test_failure_does_not_mutate_and_success_adds_once(self):
        before = copy.deepcopy(self.students)
        result = enrollCourse("S001", "CS102", self.courses, self.students, self.activities, self.rooms)
        self.assertFalse(result["success"])
        self.assertEqual(self.students, before)
        self.courses[0]["schedules"] = [{"day": 7, "period": "c"}]
        self.students[0]["maxCredits"] = 6
        before = copy.deepcopy(self.students)
        self.assertTrue(self.check()["success"])
        self.assertEqual(self.students, before)  # 純檢查不應寫入。
        self.assertTrue(enrollCourse("S001", "CS102", self.courses, self.students,
                                    self.activities, self.rooms)["success"])
        self.assertFalse(enrollCourse("S001", "CS102", self.courses, self.students,
                                     self.activities, self.rooms)["success"])
        self.assertEqual(self.students[0]["enrolledCourses"].count("CS102"), 1)

    def test_unknown_identifiers(self):
        result = checkEnrollment("missing", "missing", self.courses, self.students,
                                 self.activities, self.rooms)
        self.assertEqual(len(result["errors"]), 2)
        self.assertFalse(result["success"])

    def test_credit_limit_alone_rejects_enrollment(self):
        self.courses[0]["schedules"] = [{"day": 7, "period": "c"}]
        self.students[0]["maxCredits"] = 5
        result = self.check()
        self.assertFalse(result["success"])
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("學分超過", result["errors"][0])

    def test_missing_enrolled_record_fails_closed(self):
        self.students[0]["enrolledCourses"].append("missing")
        self.assertTrue(any("資料不存在" in e for e in self.check()["errors"]))

    def test_invalid_schedule_and_unknown_room_rejected(self):
        self.courses[0]["schedules"] = [{"day": 8, "period": "x"}]
        self.courses[0]["roomId"] = "missing"
        self.assertGreaterEqual(len(self.check()["errors"]), 2)
        self.courses[0]["schedules"] = []
        self.assertTrue(any("未設定" in e for e in self.check()["errors"]))

    def test_period_normalization_and_night_sorting(self):
        slots = [(7, "C"), (7, "b"), (7, "a"), (7, 9), (1, "1"), (7, "a")]
        self.courses[0]["schedules"] = course("x", slots)["schedules"]
        self.courses[1]["schedules"] = course("x", slots)["schedules"]
        result = self.check()
        self.assertEqual([(c["day"], c["period"]) for c in result["conflicts"]],
                         [(1, "1"), (7, "9"), (7, "a"), (7, "b"), (7, "c")])

    def test_same_time_different_room_no_room_conflict(self):
        self.assertFalse(any(c["type"] == "room" for c in self.check()["conflicts"]))
        self.courses[1]["roomId"] = "R101"
        result = self.check()
        self.assertEqual(sum(c["type"] == "room" for c in result["conflicts"]), 2)

    def test_activity_checks_courses_other_activities_and_rooms(self):
        self.activities.append(activity("A002", [(4, "5"), (2, "3")], "R101"))
        result = checkActivityParticipation("S001", "A002", self.courses, self.students,
                                            self.activities, self.rooms)
        self.assertFalse(result["success"])
        self.assertEqual({c["otherId"] for c in result["conflicts"]}, {"CS102", "MA101", "A001"})
        before = copy.deepcopy(self.students)
        self.assertFalse(joinActivity("S001", "A002", self.courses, self.students,
                                      self.activities, self.rooms)["success"])
        self.assertEqual(self.students, before)

    def test_join_activity_supports_existing_f1_students(self):
        del self.students[0]["enrolledActivities"]
        self.activities.append(activity("A002", [(6, "c")]))
        args = ("S001", "A002", self.courses, self.students, self.activities, self.rooms)
        self.assertTrue(joinActivity(*args)["success"])
        self.assertEqual(self.students[0]["enrolledActivities"], ["A002"])
        self.assertFalse(joinActivity(*args)["success"])

    def test_room_audit_includes_all_three_pair_types(self):
        courses = [course("C1", [(3, "a")]), course("C2", [(3, "a")])]
        activities = [activity("A1", [(3, "a")], "R101"), activity("A2", [(3, "a")], "R101")]
        result = checkClassroomConflicts(courses, activities)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["conflicts"]), 6)
        pairs = {(c["targetId"], c["otherId"]) for c in result["conflicts"]}
        self.assertIn(("C1", "C2"), pairs)
        self.assertIn(("C1", "A1"), pairs)
        self.assertIn(("A1", "A2"), pairs)

    def test_cli_only_persists_successful_enrollment(self):
        script = Path(__file__).with_name("f1_system.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in [("courses", self.courses), ("students", self.students),
                               ("classrooms", self.rooms), ("activities", self.activities)]:
                (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            def run(commands):
                return subprocess.run([sys.executable, "-X", "utf8", str(script)],
                                      input=commands, encoding="utf-8", capture_output=True,
                                      cwd=root, check=True, timeout=10).stdout
            self.assertIn("檢查結果：失敗", run("6\nS001\nCS102\n0\n"))
            self.assertEqual(json.loads((root / "students.json").read_text(encoding="utf-8")), self.students)
            self.courses.append(course("FREE", [(6, "b")]))
            (root / "courses.json").write_text(json.dumps(self.courses), encoding="utf-8")
            self.assertIn("檢查結果：通過", run("5\nS001\nFREE\n0\n"))
            self.assertEqual(json.loads((root / "students.json").read_text(encoding="utf-8")), self.students)
            self.assertIn("加選成功，已儲存", run("6\nS001\nFREE\n0\n"))
            stored = json.loads((root / "students.json").read_text(encoding="utf-8"))
            self.assertIn("FREE", stored[0]["enrolledCourses"])


if __name__ == "__main__":
    unittest.main()

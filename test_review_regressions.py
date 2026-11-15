"""Code Review 回歸案例：斷言需求行為，未修正的問題會正常使測試失敗。"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from f2_system import checkActivityParticipation, checkClassroomConflicts, checkEnrollment, joinActivity
from f4_system import cancelActivity, prepareActivity


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [{"roomId": "R101", "capacity": 30}, {"roomId": "R102", "capacity": 30}]
        self.students = [{"studentId": "S001", "maxCredits": 24, "enrolledCourses": [], "enrolledActivities": []}]
        self.course = {
            "courseId": "CS101", "name": "Python", "credits": 3, "maxStudents": 30,
            "roomId": "R101", "schedules": [{"day": 1, "period": "1"}],
        }

    def activity(self, aid="EV001", date="2026-10-26", room="R101"):
        data = {
            "activityId": aid, "name": aid, "activityType": "lecture", "date": date,
            "startTime": "08:10", "endTime": "09:00", "recurrence": "once",
            "expectedAttendees": 10, "requiredEquipment": [], "organizer": "測試主辦人", "roomId": room,
        }
        activity, errors = prepareActivity(data, [])
        self.assertEqual(errors, [])
        return activity

    def test_cancelled_activity_releases_room_for_course_enrollment(self):
        activities = [self.activity()]
        self.assertTrue(cancelActivity("EV001", activities, self.students)[0])
        result = checkEnrollment("S001", "CS101", [self.course], self.students, activities, self.rooms)
        self.assertTrue(result["success"], f"取消活動不應占用教室：{result}")

    def test_f2_cannot_join_cancelled_activity_or_mutate_student(self):
        activities = [self.activity()]
        self.assertTrue(cancelActivity("EV001", activities, self.students)[0])
        before = copy.deepcopy(self.students)
        result = joinActivity("S001", "EV001", [], self.students, activities, self.rooms)
        self.assertEqual((result["success"], self.students), (False, before),
                         f"取消活動應拒絕報名且不可寫入：{result}")

    def test_once_activities_on_different_dates_do_not_conflict_for_student(self):
        activities = [self.activity(), self.activity("EV002", "2026-11-02", "R102")]
        self.students[0]["enrolledActivities"] = ["EV001"]
        result = checkActivityParticipation("S001", "EV002", [], self.students, activities, self.rooms)
        self.assertTrue(result["success"], f"不同日期的單次活動不應衝堂：{result}")

    def test_once_activities_on_different_dates_can_share_room_slot(self):
        result = checkClassroomConflicts([], [self.activity(), self.activity("EV002", "2026-11-02")])
        self.assertEqual(result, {"success": True, "conflicts": [], "errors": []})

    def test_corrupt_activity_file_cannot_persist_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in [("courses", [self.course]), ("students", self.students), ("classrooms", self.rooms)]:
                (root / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            (root / "activities.json").write_text('[{"activityId":', encoding="utf-8")
            path = root / "students.json"
            before = path.read_bytes()
            completed = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(Path(__file__).with_name("f1_system.py"))],
                input="6\nS001\nCS101\n0\n", encoding="utf-8", capture_output=True, cwd=root, timeout=10,
            )
            self.assertEqual(path.read_bytes(), before,
                             f"活動資料讀取失敗後不得儲存加選。stdout={completed.stdout}; stderr={completed.stderr}")


if __name__ == "__main__":
    unittest.main()

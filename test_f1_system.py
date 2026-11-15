"""F1 公開 API 的資料驗證、刪除保護與查詢測試。"""
import copy
import tempfile
import unittest
from pathlib import Path

from f1_system import addCourse, deleteCourse, loadData, queryCourses, saveData, validateUniqueId


class CourseManagementTests(unittest.TestCase):
    def setUp(self):
        self.rooms = [{"roomId": "R101", "capacity": 30}]
        self.course = {
            "courseId": "CS101", "name": "程式設計", "credits": 3,
            "isRequired": True, "teacher": "王老師", "maxStudents": 2,
            "roomId": "R101", "schedules": [{"day": 1, "period": "1"}, {"day": 3, "period": "a"}],
        }

    def test_add_course_preserves_all_meetings(self):
        courses = []
        self.assertTrue(addCourse(copy.deepcopy(self.course), courses, self.rooms)[0])
        self.assertEqual(courses, [self.course])

    def test_duplicate_course_does_not_change_existing_data(self):
        courses = [copy.deepcopy(self.course)]
        self.assertFalse(addCourse(copy.deepcopy(self.course), courses, self.rooms)[0])
        self.assertEqual(courses, [self.course])

    def test_student_id_uniqueness(self):
        students = [{"studentId": "S001"}]
        self.assertFalse(validateUniqueId("S001", students, "studentId")[0])
        self.assertTrue(validateUniqueId("S002", students, "studentId")[0])

    def test_invalid_credits_capacity_slots_and_room_leave_list_empty(self):
        invalid = [
            {"credits": 0}, {"credits": -1}, {"credits": 1.5},
            {"maxStudents": 0}, {"maxStudents": -1},
            {"schedules": [{"day": 0, "period": "1"}]},
            {"schedules": [{"day": 8, "period": "1"}]},
            {"schedules": [{"day": 1, "period": "d"}]}, {"roomId": "missing"},
        ]
        for change in invalid:
            with self.subTest(change=change):
                candidate = dict(copy.deepcopy(self.course), **change)
                courses = []
                self.assertFalse(addCourse(candidate, courses, self.rooms)[0])
                self.assertEqual(courses, [])

    def test_delete_enrolled_course_rejected_then_allowed_after_withdrawal(self):
        courses = [copy.deepcopy(self.course)]
        students = [{"studentId": "S001", "enrolledCourses": ["CS101"]}]
        self.assertFalse(deleteCourse("CS101", courses, students)[0])
        self.assertEqual(courses, [self.course])
        students[0]["enrolledCourses"].clear()
        self.assertTrue(deleteCourse("CS101", courses, students)[0])
        self.assertEqual(courses, [])

    def test_deleting_unknown_course_preserves_list(self):
        courses = [copy.deepcopy(self.course)]
        self.assertFalse(deleteCourse("missing", courses, [])[0])
        self.assertEqual(courses, [self.course])

    def test_query_combines_filters_and_distinguishes_full_courses(self):
        other = dict(copy.deepcopy(self.course), courseId="CS102", teacher="李老師", isRequired=False)
        courses = [self.course, other]
        students = [{"studentId": sid, "enrolledCourses": ["CS101"]} for sid in ("S001", "S002")]
        full = queryCourses(courses, students, qId="CS", qTeacher="王", qDay=3, qReq=True, qVacancy=False)
        self.assertEqual([c["courseId"] for c in full], ["CS101"])
        self.assertEqual([c["courseId"] for c in queryCourses(courses, students, qVacancy=True)], ["CS102"])
        self.assertEqual(len(queryCourses(courses, students)), 2)
        self.assertEqual(queryCourses(courses, students, qTeacher="王", qReq=False), [])

    def test_json_roundtrip_retains_chinese_and_enrollments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "courses.json"
            saveData(path, [self.course])
            self.assertEqual(loadData(path), [self.course])
            self.assertIn("程式設計", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

import unittest

from f3_system import (
    buildTimetable, queryTimetable, findFreeBlocks, summarizeTimetable,
    formatTimetable, formatSummary, formatFreeBlocks,
)


def course(cid, slots, credits=3, room="R101"):
    return {
        "courseId": cid, "name": cid, "credits": credits, "roomId": room,
        "schedules": [{"day": day, "period": period} for day, period in slots],
    }


def activity(aid, slots, recurrence="weekly", date="2026-11-05", status="scheduled"):
    return {
        "activityId": aid, "name": aid, "roomId": "R102", "recurrence": recurrence,
        "date": date, "status": status,
        "schedules": [{"day": day, "period": period} for day, period in slots],
    }


class TimetableTests(unittest.TestCase):
    def setUp(self):
        # 星期一：CS101 第 1-2 節、MA101 第 6 節（同一天多門課，中間空 3 節）
        # 星期三：CS101 第 3 節（同一課程一週多次上課）
        # 星期四：EV001 單次活動第 5 節
        self.courses = [
            course("CS101", [(1, "1"), (1, "2"), (3, "3")], credits=3),
            course("MA101", [(1, "6")], credits=2),
        ]
        self.activities = [activity("EV001", [(4, "5")], recurrence="once")]
        self.students = [{
            "studentId": "S001", "name": "林小華", "maxCredits": 24,
            "enrolledCourses": ["CS101", "MA101"], "enrolledActivities": ["EV001"],
        }]
        self.timetable, self.errors = buildTimetable(
            "S001", self.courses, self.students, self.activities
        )

    def test_matrix_is_monday_to_sunday_by_12_periods(self):
        self.assertEqual(len(self.timetable), 7)
        self.assertTrue(all(len(day) == 12 for day in self.timetable))
        self.assertEqual(self.errors, [])

    def test_course_meeting_several_times_fills_every_slot(self):
        found = [(d, p) for d, p, _ in queryTimetable(self.timetable, itemId="cs101")]
        self.assertEqual(found, [(1, "1"), (1, "2"), (3, "3")])

    def test_several_courses_on_same_day(self):
        ids = [entry["id"] for _, _, entry in queryTimetable(self.timetable, day=1)]
        self.assertEqual(ids, ["CS101", "CS101", "MA101"])

    def test_query_by_period_accepts_uppercase(self):
        self.timetable[4][9].append({"kind": "course", "id": "X", "name": "X", "roomId": None,
                                     "recurrence": "weekly", "date": None})
        [(day, period, _)] = queryTimetable(self.timetable, period="A")
        self.assertEqual((day, period), (5, "a"))

    def test_three_consecutive_free_periods(self):
        blocks, errors = findFreeBlocks(self.timetable, 1, 1, "3", "5", minLength=3)
        self.assertEqual(errors, [])
        self.assertEqual(blocks, [{"day": 1, "startPeriod": "3", "endPeriod": "5", "length": 3}])

    def test_monday_to_wednesday_query_lists_each_day(self):
        blocks, errors = findFreeBlocks(self.timetable, 1, 3, "1", "9", minLength=3)
        self.assertEqual(errors, [])
        self.assertEqual([(b["day"], b["startPeriod"], b["endPeriod"]) for b in blocks],
                         [(1, "3", "5"), (1, "7", "9"), (2, "1", "9"), (3, "4", "9")])
        self.assertIn("星期二 第 1～9 節（9 節）", formatFreeBlocks(blocks, 1, 3, "1", "9", 3))

    def test_friday_to_monday_is_invalid(self):
        blocks, errors = findFreeBlocks(self.timetable, 5, 1, "1", "9")
        self.assertEqual(blocks, [])
        self.assertTrue(errors[0].startswith("[INVALID_TIME_RANGE]"))

    def test_start_period_after_end_period_is_error(self):
        _, errors = findFreeBlocks(self.timetable, 1, 1, "5", "3")
        self.assertTrue(errors[0].startswith("[INVALID_TIME_RANGE]"))

    def test_min_length_longer_than_range_returns_empty_not_error(self):
        blocks, errors = findFreeBlocks(self.timetable, 2, 2, "1", "3", minLength=5)
        self.assertEqual((blocks, errors), ([], []))
        self.assertIn("此範圍內沒有符合條件的空閒時段", formatFreeBlocks(blocks, 2, 2, "1", "3", 5))

    def test_illegal_day_and_period_are_errors(self):
        _, errors = findFreeBlocks(self.timetable, 0, 8, "1", "d", minLength=0)
        self.assertEqual(len(errors), 4)

    def test_summary_counts_periods_credits_and_gaps(self):
        summary = summarizeTimetable(self.timetable, "S001", self.courses, self.students)
        self.assertEqual(summary["periodsPerDay"], [3, 0, 1, 1, 0, 0, 0])
        self.assertEqual(summary["totalCredits"], 5)
        self.assertEqual(summary["totalGaps"], 3)
        self.assertIn("每日節數：一 3｜二 0｜三 1｜四 1", formatSummary(summary))
        self.assertIn("空堂數：3", formatSummary(summary))

    def test_display_marks_activities_conflicts_and_once_dates(self):
        self.courses.append(course("PH101", [(1, "1")]))
        self.students[0]["enrolledCourses"].append("PH101")
        timetable, _ = buildTimetable("S001", self.courses, self.students, self.activities)
        text = formatTimetable(timetable, "S001", self.students, 8)
        self.assertIn("學生：S001 林小華 本週總學分：8", text)
        self.assertIn("*EV001", text)
        self.assertIn("!衝突", text)
        self.assertIn("!衝突：星期一第1節 CS101、PH101", text)
        self.assertIn("*EV001 EV001：2026-11-05（單次活動）", text)

    def test_empty_timetable_message(self):
        self.students.append({"studentId": "S002", "name": "空", "enrolledCourses": []})
        timetable, errors = buildTimetable("S002", self.courses, self.students, self.activities)
        self.assertEqual(errors, [])
        self.assertIn("目前沒有已選課程", formatTimetable(timetable, "S002", self.students, 0))

    def test_cancelled_activity_is_not_shown(self):
        self.activities[0]["status"] = "cancelled"
        timetable, _ = buildTimetable("S001", self.courses, self.students, self.activities)
        self.assertEqual(queryTimetable(timetable, itemId="EV001"), [])

    def test_unknown_student_and_missing_course_are_reported(self):
        _, errors = buildTimetable("S999", self.courses, self.students, self.activities)
        self.assertEqual(errors, ["[NOT_FOUND] 找不到學生：S999"])
        self.students[0]["enrolledCourses"].append("GONE")
        _, errors = buildTimetable("S001", self.courses, self.students, self.activities)
        self.assertEqual(errors, ["[NOT_FOUND] 已選課程資料不存在：GONE"])


if __name__ == "__main__":
    unittest.main()

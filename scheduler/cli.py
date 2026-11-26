"""F1–F7 命令列輸入輸出；既有選單呼叫本模組，不混入服務層。"""
import re

from f5_system import filterCourses
from .filter_display import format_filter_report
from .models import FilterCriteria
from .timeslot import PERIODS
from .storage import save_all
from .result import ErrorItem, Result
from .operations import apply_operation
from .storage_bridge import legacy_views, record_dict
from .optimizer import search_best_timetables
from .optimizer_display import format_optimizer_report
from .models import ScoreWeights, SystemData


def _tokens(text: str) -> list[str]:
    return [item for item in re.split(r"[\s,，、;；]+", text.strip()) if item]


def run_filter(courses: list | dict, students: list | dict,
               activities: list | dict, classrooms: list | dict) -> None:
    """詢問 F5 六項條件，顯示篩選報告；非法輸入顯示錯誤，不修改資料。"""
    print("\n--- F5 多條件課程篩選與可行性檢查 ---")
    sid = input("學號：").strip()
    desired = _tokens(input("希望修習課程（逗號或空白分隔，可留空）："))
    required = _tokens(input("必修課程（逗號或空白分隔，可留空）："))
    minimum = input("最低學分（預設 0）：").strip()
    maximum = input("最高學分（預設為學生上限）：").strip()
    blocked = _tokens(input("不可上課時段（如 2-3,5-a；星期五全天輸入 5-*）："))
    preferred = _tokens(input("偏好星期（如 1,2,3；留空不限）："))
    try:
        student_rows = students.get("records", []) if isinstance(students, dict) else students
        student = next((item for item in student_rows
                        if str(item.get("student_id", item.get("studentId", ""))).strip().upper() == sid.upper()), {})
        limit = student.get("credit_limit", student.get("maxCredits", 25))
        expanded = []
        for slot in blocked:
            if re.fullmatch(r"[1-7]-\*", slot):
                expanded.extend(f"{slot[0]}-{period}" for period in PERIODS)
            else:
                expanded.append(slot)
        criteria = FilterCriteria(desired, required, int(minimum or 0),
                                  int(maximum) if maximum else limit, expanded,
                                  [int(day) for day in preferred])
    except (ValueError, TypeError):
        print("[INVALID_VALUE] 學分與偏好星期必須輸入整數。")
        return
    print(format_filter_report(filterCourses(sid, criteria, courses, students, activities, classrooms)))


def show_load_report(report) -> None:
    """顯示五類檔案載入摘要與錯誤，檔案不完整時提示唯讀保護。"""
    print(report.format_text())
    if not report.safe_to_save:
        print("資料檔有錯誤，本次工作階段暫停修改與儲存；請確認報告與備份後重新啟動。")


def run_optimizer(data: SystemData) -> None:
    """收集 F7 條件與可調權重，顯示排名、課表及錯誤，不儲存資料。"""
    print("\n--- F7 最佳課表搜尋 ---")
    sid = input("學號：").strip().upper()
    desired = _tokens(input("候選選修課程（逗號或空白分隔，可留空）："))
    required = _tokens(input("必修課程（逗號或空白分隔，可留空）："))
    minimum = input("最低總學分（預設 0，包含已選）：").strip()
    maximum = input("最高總學分（預設學生上限）：").strip()
    blocked = _tokens(input("不可上課時段（如 2-3,5-a；星期五全天 5-*）："))
    days = _tokens(input("偏好星期（如 1,2,3；留空不限）："))
    preferred = _tokens(input("偏好課程（留空採候選選修清單）："))
    limit = input("顯示前幾組（預設 5；all 為全部）：").strip().lower()
    weight_text = _tokens(input("權重：到校天數,空堂,早八,跨度,偏好課程,偏好星期（預設 5,2,3,1,10,5）："))
    try:
        student = data.students.get(sid)
        credit_limit = record_dict(student)["credit_limit"] if student else 25
        forbidden = []
        for slot in blocked:
            forbidden.extend([f"{slot[0]}-{p}" for p in PERIODS]
                             if re.fullmatch(r"[1-7]-\*", slot) else [slot])
        criteria = FilterCriteria(desired, required, int(minimum or 0),
                                  int(maximum) if maximum else credit_limit,
                                  forbidden, [int(day) for day in days])
        if weight_text and len(weight_text) != 6:
            raise ValueError("權重須輸入六個數值")
        weights = ScoreWeights(*map(float, weight_text)) if weight_text else ScoreWeights()
        top_k = None if limit == "all" else int(limit or 5)
    except (ValueError, TypeError) as exc:
        print(f"[INVALID_VALUE] 輸入格式錯誤：{exc}")
        return
    result = search_best_timetables(data, sid, criteria, weights=weights,
                                    preferred_courses=preferred or None, top_k=top_k)
    print(format_optimizer_report(result))


def show_initialization(result: Result) -> None:
    """顯示示範資料初始化結果，不隱藏覆寫保護錯誤。"""
    print(result.data if result.ok else "\n".join(f"[{error.code}] {error.message}" for error in result.errors))


def commit_operation(data, operation: Result, data_dir: str) -> Result:
    """只在五檔儲存成功後更新目前工作階段，失敗時保留原記憶體資料。"""
    if not operation.ok:
        return operation
    saved = save_all(operation.data, data_dir)
    if saved.ok:
        data.__dict__.update(operation.data.__dict__)
    return saved


def _show_courses(data) -> None:
    for code, value in sorted(data.courses.items()):
        course = record_dict(value)
        count = sum(code in record_dict(student)["enrolled_courses"] for student in data.students.values())
        print(f"{code} {course['name']} {course['credits']}學分 {count}/{course['capacity']}人 {course['status']}")
    if not data.courses:
        print("目前沒有課程；可先使用 --init-demo --data-dir demo-data 建立獨立示範資料。")


def run(data, data_dir: str = "data", writable: bool = True) -> None:
    """F6 整合選單：每次成功修改自動儲存，檢查或錯誤操作不寫檔。"""
    actions = {"2": "add", "3": "drop", "4": "register", "7": "cancel_activity"}
    while True:
        print("\n--- v1 選課系統／F6 資料儲存 ---")
        print("1. 查詢課程  2. 加選  3. 退選  4. 報名活動  5. F5篩選")
        print("6. 資料摘要  7. 取消活動  8. 手動儲存  9. F7最佳課表搜尋  0. 離開")
        try:
            choice = input("請選擇操作：").strip()
            if choice == "0":
                return
            if choice == "1":
                _show_courses(data)
            elif choice == "5":
                views = legacy_views(data)
                run_filter(views["courses"], views["students"], views["activities"], views["classrooms"])
            elif choice == "6":
                print(f"課程 {len(data.courses)}、學生 {len(data.students)}、教室 {len(data.classrooms)}、活動 {len(data.activities)}、選課紀錄 {len(data.enrollment_log)}")
            elif choice == "9":
                run_optimizer(data)
            elif choice in actions or choice == "8":
                if not writable:
                    print("[SAVE_FAILED] 載入資料不完整，拒絕修改與儲存。")
                    continue
                if choice == "8":
                    result = save_all(data, data_dir)
                else:
                    sid = "" if choice == "7" else input("學號：").strip()
                    code = input("課程代號：" if choice in ("2", "3") else "活動代號：").strip()
                    result = commit_operation(data, apply_operation(data, actions[choice], sid, code), data_dir)
                if result.ok:
                    print("操作成功，已儲存五類資料。")
                else:
                    print("\n".join(f"[{error.code}] {error.message}" for error in result.errors))
            else:
                print("無效的選項。")
        except (EOFError, KeyboardInterrupt):
            print("\n離開系統；未提交的操作沒有儲存。")
            return


def _legacy_commit(filename, records, previous):
    from .storage import save_legacy_file
    result = save_legacy_file(filename, records)
    if not result.ok:
        records[:] = previous
        print("\n".join(f"[{error.code}] {error.message}" for error in result.errors))
    return result.ok


def run_legacy():
    from copy import deepcopy
    from f1_system import loadData, addCourse, deleteCourse, queryCourses, getEnrolledCount
    from f2_system import (
        checkEnrollment, enrollCourse, checkActivityParticipation, joinActivity,
        checkClassroomConflicts, formatResult, DAYS,
    )

    courses = loadData("courses.json")
    students = loadData("students.json")
    classrooms = loadData("classrooms.json")
    activities = loadData("activities.json")

    for records in (courses, students, classrooms, activities):
        for error in getattr(records, "load_errors", []):
            print(error)

    while True:
        previous_courses, previous_students = deepcopy(courses), deepcopy(students)
        print("\n--- 課程與學生資料管理 (F1)／多層次衝堂與選課檢查 (F2) ---")
        print("1. 新增課程")
        print("2. 刪除課程")
        print("3. 查詢課程")
        print("4. 列出所有學生")
        print("5. 檢查加選（不儲存）")
        print("6. 加選課程")
        print("7. 檢查活動（不儲存）")
        print("8. 參加活動")
        print("9. 檢查所有教室衝堂")
        print("10. 列出活動")
        print("11. 多條件課程篩選與可行性檢查 (F5)")
        print("12. 最佳課表搜尋 (F7)")
        print("0. 離開系統")

        choice = input("請選擇操作: ").strip()

        if choice in ("1", "2", "6", "8") and any(
            getattr(records, "load_errors", []) for records in (courses, students, classrooms, activities)
        ):
            print("[SAVE_FAILED] 資料載入失敗，本次拒絕修改與儲存；請修復資料後重新啟動。")
            continue

        if choice == "1":
            courseId = input("課程代號: ").strip()
            name = input("課程名稱: ").strip()

            # 防止學分輸入非數字時造成程式中斷。
            try:
                credits = int(input("學分: "))
                maxStudents = int(input("人數上限: "))
                day = int(input("星期 (1-7): "))
            except ValueError:
                print("錯誤：學分、人數上限及星期必須輸入整數。")
                continue

            isReqStr = input("是否必修 (y/n): ").strip().lower()
            if isReqStr not in ("y", "n"):
                print("錯誤：請輸入 y 或 n。")
                continue

            isReq = isReqStr == "y"
            teacher = input("授課教師: ").strip()
            room = input("教室代號: ").strip()
            period = input("節次 (1-9,a,b,c): ").strip().lower()

            newCourse = {
                "courseId": courseId,
                "name": name,
                "credits": credits,
                "isRequired": isReq,
                "teacher": teacher,
                "maxStudents": maxStudents,
                "roomId": room,
                "schedules": [{"day": day, "period": period}],
            }

            success, msg = addCourse(newCourse, courses, classrooms)
            print(msg)

            if success:
                _legacy_commit("courses.json", courses, previous_courses)

        elif choice == "2":
            courseId = input("輸入欲刪除的課程代號: ").strip()

            success, msg = deleteCourse(courseId, courses, students)
            print(msg)

            if success:
                _legacy_commit("courses.json", courses, previous_courses)

        elif choice == "3":
            print("直接按 Enter 略過該條件")

            qId = input("課程代號: ").strip() or None
            qTeacher = input("教師名稱: ").strip() or None
            qDay = input("星期: ").strip() or None

            qReqStr = input("是否必修 (y/n): ").strip().lower()

            if qReqStr == "y":
                qReq = True
            elif qReqStr == "n":
                qReq = False
            else:
                qReq = None

            qVacStr = (
                input("是否須有剩餘名額 (y/n，Enter 略過): ").strip().lower()
            )

            # 修正：n 代表只查詢額滿課程；Enter 才是不篩選。
            if qVacStr == "y":
                qVac = True
            elif qVacStr == "n":
                qVac = False
            else:
                qVac = None

            results = queryCourses(
                courses, students, qId, qTeacher, qDay, qReq, qVac
            )

            print(f"\n--- 查詢結果 (共 {len(results)} 筆) ---")

            for result in results:
                print(
                    f"[{result['courseId']}] {result['name']}\n"
                    f"{result['teacher']} "
                    f"(學分:{result['credits']}, "
                    f"上限:{result['maxStudents']})"
                )

                enrolled = getEnrolledCount(result["courseId"], students)
                remaining = result["maxStudents"] - enrolled

                print(
                    f"已選修人數：{enrolled}，"
                    f"剩餘名額：{remaining}"
                )

        elif choice == "4":
            print(f"\n--- 學生列表 (共 {len(students)} 筆) ---")

            for student in students:
                print(
                    f"{student['studentId']}\n"
                    f"{student['name']} "
                    f"({student['department']})"
                )

        elif choice in ("5", "6", "7", "8"):
            studentId = input("學號: ").strip()
            isCourse = choice in ("5", "6")
            targetId = input("課程代號: " if isCourse else "活動代號: ").strip()
            operation = {
                "5": checkEnrollment, "6": enrollCourse,
                "7": checkActivityParticipation, "8": joinActivity,
            }[choice]
            result = operation(studentId, targetId, courses, students, activities, classrooms)
            print(formatResult(result))
            if result["success"] and choice in ("6", "8"):
                if not _legacy_commit("students.json", students, previous_students):
                    continue
                print("加選成功，已儲存。" if isCourse else "活動報名成功，已儲存。")

        elif choice == "9":
            result = checkClassroomConflicts(courses, activities)
            for number, conflict in enumerate(result["conflicts"], 1):
                print(
                    f"衝突{number}：教室 {conflict['roomId']} "
                    f"星期{DAYS[conflict['day'] - 1]}第{conflict['period']}節\n"
                    f"{conflict['targetId']} {conflict['targetName']}／"
                    f"{conflict['otherId']} {conflict['otherName']}"
                )
            for message in result["errors"]:
                print(f"錯誤：{message}")
            if result["success"]:
                print("所有教室配置檢查通過。")

        elif choice == "10":
            for activity in activities:
                print(f"{activity['activityId']} {activity['name']}（教室 {activity.get('roomId', '未設定')}）")
            if not activities:
                print("尚無活動，請依 README 格式設定 activities.json。")

        elif choice == "11":
            from scheduler.cli import run_filter
            run_filter(courses, students, activities, classrooms)

        elif choice == "12":
            from .adapters import system_data_from_records
            try:
                data = system_data_from_records(courses, students, activities, classrooms)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                print(f"[INVALID_VALUE] 資料無法載入：{exc}")
                continue
            run_optimizer(data)

        elif choice == "0":
            print("系統結束。")
            break

        else:
            print("無效的選項。")

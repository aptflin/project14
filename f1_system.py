import json
import os

# Data Access
def load_data(filename):
    """讀取 JSON 檔案，確保單一錯誤不中斷程式"""
    if not os.path.exists(filename):
        return []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"錯誤：{filename} 格式異常。")
        return []

def save_data(filename, data):
    """儲存資料至 JSON 檔案"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 資料驗證邏輯 (Validation)
def validate_unique_id(new_id, existing_data, id_key):
    for item in existing_data:
        if item.get(id_key) == new_id:
            return False, f"錯誤：代號 '{new_id}' 已存在，不得重複。" 
    return True, ""

def validate_course_params(credits, max_students):
    if not isinstance(credits, int) or credits <= 0:
        return False, "錯誤：學分必須為正整數。" 
    if not isinstance(max_students, int) or max_students < 1:
        return False, "錯誤：課程人數上限不得小於 1。" 
    return True, ""

def validate_schedule(day, period):
    if not isinstance(day, int) or not (1 <= day <= 7):
        return False, "錯誤：星期僅限 1-7。" 
    valid_periods = [str(i) for i in range(1, 10)] + ['a', 'b', 'c', 'A', 'B', 'C']
    if str(period) not in valid_periods:
        return False, "錯誤：節次僅限 1-9、a、b、c。" 
    return True, ""

def validate_course_deletion(course_id, students_data):
    for student in students_data:
        if course_id in student.get("enrolled_courses", []):
            return False, f"錯誤：學生 {student['student_id']} 已選修，拒絕刪除。" 
    return True, ""

# 核心模組 (Core Functions)能獨立測試
def add_course(course_data, courses_list, classrooms_list):
    is_valid, msg = validate_unique_id(course_data['course_id'], courses_list, 'course_id')
    if not is_valid: return False, msg
    
    is_valid, msg = validate_course_params(course_data['credits'], course_data['max_students'])
    if not is_valid: return False, msg
    
    for sch in course_data.get('schedules', []):
        is_valid, msg = validate_schedule(sch['day'], sch['period'])
        if not is_valid: return False, msg

    valid_rooms = [r['room_id'] for r in classrooms_list]
    if course_data['room_id'] not in valid_rooms:
        return False, "錯誤：教室代號不存在。"

    courses_list.append(course_data)
    return True, "新增成功"

def delete_course(course_id, courses_list, students_list):
    is_valid, msg = validate_course_deletion(course_id, students_list)
    if not is_valid: return False, msg
    
    for i, c in enumerate(courses_list):
        if c['course_id'] == course_id:
            del courses_list[i]
            return True, "刪除成功"
    return False, "找不到該課程"

def get_enrolled_count(course_id, students_list):
    count = 0
    for s in students_list:
        if course_id in s.get("enrolled_courses", []):
            count += 1
    return count

def query_courses(courses_list, students_list, q_id=None, q_teacher=None, q_day=None, q_req=None, q_vacancy=None):
    # 多條件查詢
    results = []
    for c in courses_list:
        if q_id and q_id not in c['course_id']: continue
        if q_teacher and q_teacher not in c['teacher']: continue
        if q_req is not None and c['is_required'] != q_req: continue
        
        if q_day:
            days = [str(sch['day']) for sch in c.get('schedules', [])]
            if str(q_day) not in days: continue
            
        if q_vacancy:
            enrolled = get_enrolled_count(c['course_id'], students_list)
            if c['max_students'] - enrolled <= 0: continue
            
        results.append(c)
    return results
# CLI 介面層
def main():
    # 啟動時載入資料
    courses = load_data('courses.json')
    students = load_data('students.json')
    classrooms = load_data('classrooms.json')

    while True:
        print("\n--- 課程與學生資料管理 (F1) ---")
        print("1. 新增課程")
        print("2. 刪除課程")
        print("3. 查詢課程")
        print("4. 列出所有學生")
        print("0. 離開系統")
        choice = input("請選擇操作: ")

        if choice == '1':
            c_id = input("課程代號: ")
            name = input("課程名稱: ")
            credits = int(input("學分: "))
            is_req = input("是否必修 (y/n): ").lower() == 'y'
            teacher = input("授課教師: ")
            max_stu = int(input("人數上限: "))
            room = input("教室代號: ")
            
            day = int(input("星期 (1-7): "))
            period = input("節次 (1-9,a,b,c): ")
            
            new_course = {
                "course_id": c_id, "name": name, "credits": credits,
                "is_required": is_req, "teacher": teacher,
                "max_students": max_stu, "room_id": room,
                "schedules": [{"day": day, "period": period.lower()}]
            }
            # 透過參數傳遞
            success, msg = add_course(new_course, courses, classrooms)
            print(msg)
            if success: save_data('courses.json', courses)

        elif choice == '2':
            c_id = input("輸入欲刪除的課程代號: ")
            success, msg = delete_course(c_id, courses, students)
            print(msg)
            if success: save_data('courses.json', courses)

        elif choice == '3':
            print("直接按 Enter 略過該條件")
            q_id = input("課程代號: ") or None
            q_teacher = input("教師名稱: ") or None
            q_day = input("星期: ") or None
            q_req_str = input("是否必修 (y/n): ")
            q_req = True if q_req_str.lower() == 'y' else (False if q_req_str.lower() == 'n' else None)
            q_vac_str = input("是否須有剩餘名額 (y/n): ")
            q_vac = True if q_vac_str.lower() == 'y' else None

            results = query_courses(courses, students, q_id, q_teacher, q_day, q_req, q_vac)
            print(f"\n--- 查詢結果 (共 {len(results)} 筆) ---")
            for r in results:
                print(f"[{r['course_id']}] {r['name']} - {r['teacher']} (學分:{r['credits']}, 上限:{r['max_students']})")

        elif choice == '4':
            print(f"\n--- 學生列表 (共 {len(students)} 筆) ---")
            for s in students:
                print(f"{s['student_id']} - {s['name']} ({s['department']})")

        elif choice == '0':
            print("系統結束。")
            break
        else:
            print("無效的選項。")

if __name__ == "__main__":
    main()
"""每個 F5 測試建立獨立記憶體資料，不使用正式 JSON。"""
import pytest

from scheduler.models import Activity, Course, Student, SystemData


@pytest.fixture
def sample_data():
    return SystemData(
        courses={
            "CS101": Course("CS101", "Python", 3, "required", "王老師", 10, "EE-101", ["1-1", "1-2"]),
            "MA101": Course("MA101", "微積分", 3, "required", "陳老師", 10, "SCI-201", ["2-3", "2-4"]),
            "EN101": Course("EN101", "英文", 2, "elective", "李老師", 10, "LIB-101", ["3-7"]),
            "PH101": Course("PH101", "物理", 3, "elective", "林老師", 10, "SCI-201", ["4-1"]),
        },
        students={"S001": Student("S001", "測試學生", "資工二", 24),
                  "S002": Student("S002", "其他學生", "資工一", 25)},
        activities={"EV001": Activity("EV001", "讀書會", "2026-10-29", "12:10", "13:00",
                                        "weekly", "LIB-101", ["S001"])},
    )

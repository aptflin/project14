"""使用標準函式庫執行全套測試，產生 HTML／JSON／文字報告。"""
import argparse
from datetime import datetime, timezone
from html import escape
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import xml.etree.ElementTree as ET


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def record(self, test, status, detail=""):
        self.records.append({"test": test.id(), "status": status, "detail": detail,
                             "seconds": round(time.perf_counter() - self.started, 4)})

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "FAIL", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "ERROR", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, "SKIP", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, "EXPECTED_FAILURE", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, "UNEXPECTED_SUCCESS")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            status = "FAIL" if issubclass(err[0], test.failureException) else "ERROR"
            self.record(subtest, status, self._exc_info_to_string(err, test))


def run_pytest_files(root, pattern, report_dir):
    """將新增的 pytest 案例納入同一份 HTML／JSON 報告。"""
    paths = sorted((root / "tests").glob(pattern))
    if not paths:
        return [], "", True
    xml_path = report_dir / "pytest.xml"
    completed = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "pytest", "-q",
         f"--junitxml={xml_path}", *map(str, paths)],
        cwd=root, capture_output=True, encoding="utf-8", errors="replace",
    )
    output = completed.stdout + completed.stderr
    records = []
    # 不讀取先前可能留下的 XML：只有本次 pytest 正常產生報告才接受。
    if completed.returncode in (0, 1, 2) and xml_path.exists() and "generated xml file" in output:
        for case in ET.parse(xml_path).iter("testcase"):
            status, detail = "PASS", ""
            for tag, label in (("failure", "FAIL"), ("error", "ERROR"), ("skipped", "SKIP")):
                child = case.find(tag)
                if child is not None:
                    status, detail = label, child.text or child.get("message", "")
                    break
            records.append({"test": f"{case.get('classname', '')}.{case.get('name', '')}",
                            "status": status, "detail": detail, "seconds": float(case.get("time", 0))})
    if not records:
        records.append({"test": "pytest.collection", "status": "ERROR", "detail": output,
                        "seconds": 0})
    return records, output, completed.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pattern", default="test_*.py", help="測試檔名模式，預設執行全部")
    parser.add_argument("--report-dir", default="test-results", help="報告目錄，相對路徑以專案目錄為基準")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = root / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    # 舊有命令列測試會啟動子 Python，讓子程序也避免產生快取。
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    suite = unittest.defaultTestLoader.discover(str(root), pattern=args.pattern, top_level_dir=str(root))
    stream = io.StringIO()
    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
    extra_records, extra_text, extra_ok = run_pytest_files(root, args.pattern, report_dir)
    result.records.extend(extra_records)
    text = (stream.getvalue() if result.testsRun else "") + extra_text
    print(text, end="")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "successful": result.wasSuccessful() and extra_ok and result.testsRun + len(extra_records) > 0,
        "tests": result.testsRun + len(extra_records),
        "passed": sum(row["status"] == "PASS" for row in result.records),
        "failures": len(result.failures) + sum(row["status"] == "FAIL" for row in extra_records),
        "errors": len(result.errors) + sum(row["status"] == "ERROR" for row in extra_records),
        "skipped": len(result.skipped) + sum(row["status"] == "SKIP" for row in extra_records),
        "expected_failures": len(result.expectedFailures), "unexpected_successes": len(result.unexpectedSuccesses),
        "seconds": round(time.perf_counter() - started, 4),
    }
    if not summary["tests"]:
        text += "ERROR: No tests were discovered.\n"
        print("ERROR: No tests were discovered.")
    (report_dir / "results.json").write_text(
        json.dumps({"summary": summary, "results": result.records}, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "results.txt").write_text(text, encoding="utf-8")
    rows = "".join(
        f"<tr><td>{escape(row['test'])}</td><td>{escape(row['status'])}</td>"
        f"<td>{row['seconds']}</td><td><pre>{escape(row['detail'])}</pre></td></tr>"
        for row in result.records
    )
    html = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>project14 自動化測試報告</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#222}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:.6rem;text-align:left;vertical-align:top}}th{{background:#eee}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}}td:first-child{{overflow-wrap:anywhere}}</style>
<h1>project14 自動化測試報告</h1><p>UTC：{escape(summary['generated_at'])}</p>
<p>總計 {summary['tests']} 項｜通過 {summary['passed']}｜失敗 {summary['failures']}｜錯誤 {summary['errors']}｜略過 {summary['skipped']}</p>
<p>結果：{'通過' if summary['successful'] else '未通過'}。子案例失敗亦會列出；詳細統計請見 results.json。</p>
<table><thead><tr><th>案例</th><th>結果</th><th>秒數</th><th>錯誤詳情</th></tr></thead><tbody>{rows}</tbody></table></html>'''
    (report_dir / "report.html").write_text(html, encoding="utf-8")
    print(f"Report: {report_dir / 'report.html'}")
    return 0 if summary["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

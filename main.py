"""v1 系統入口：F6 載入所有資料，再交給 CLI；預設資料夾 data/。"""
import argparse

from scheduler.cli import run, show_initialization, show_load_report
from scheduler.storage import initialize_demo, load_all


def main() -> int:
    """解析資料夾參數、載入 F6 資料與報告，啟動互動選單。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="v1 五類 JSON 所在資料夾")
    parser.add_argument("--init-demo", action="store_true", help="只在沒有既有資料檔時建立示範資料")
    args = parser.parse_args()
    if args.init_demo:
        result = initialize_demo(args.data_dir)
        show_initialization(result)
        return 0 if result.ok else 1
    data, report = load_all(args.data_dir)
    show_load_report(report)
    run(data, data_dir=args.data_dir, writable=report.safe_to_save)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

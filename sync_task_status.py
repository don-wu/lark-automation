import json
import subprocess
import sys
from datetime import datetime

BASE_TOKEN = "Mg9ZbeiFrah1xdsH31XcuDRanTf"
LARK_CLI = "lark-cli.cmd" if sys.platform == "win32" else "lark-cli"
TRACKING_TABLE_ID = "tblRWIWq1HDwknuq"


def run_cli(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    if not result.stdout.strip():
        raise RuntimeError(f"lark-cli returned empty stdout. stderr={result.stderr!r} args={args}")
    payload = json.loads(result.stdout)
    if "ok" in payload:
        if not payload.get("ok"):
            raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    else:
        if payload.get("code", 0) != 0:
            raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return payload["data"]


def record_list(table_id):
    return run_cli([
        LARK_CLI, "--as", "bot", "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", table_id,
        "--limit", "200",
        "--format", "json",
    ])


def record_upsert(table_id, record_id, values):
    args = [
        LARK_CLI, "--as", "bot", "base", "+record-upsert",
        "--base-token", BASE_TOKEN,
        "--table-id", table_id,
        "--record-id", record_id,
        "--json", json.dumps(values, ensure_ascii=False),
    ]
    return run_cli(args)


def get_lark_task(task_guid):
    data = run_cli([
        LARK_CLI, "--as", "bot", "task", "tasks", "get",
        "--params", json.dumps({"task_guid": task_guid}),
        "--format", "json",
    ])
    return data.get("task") or data


def rows_by_fields(payload):
    fields = payload["fields"]
    rows = []
    for record_id, values in zip(payload["record_id_list"], payload["data"]):
        row = dict(zip(fields, values))
        row["_record_id"] = record_id
        rows.append(row)
    return rows


def select_value(value):
    if isinstance(value, list) and value:
        return value[0]
    return value


def main():
    rows = rows_by_fields(record_list(TRACKING_TABLE_ID))
    now = datetime.now()
    for row in rows:
        if select_value(row.get("完成状态")) != "待完成":
            continue
        task_id = row.get("飞书任务ID") or ""
        task_id = task_id.strip() if isinstance(task_id, str) else ""
        if not task_id:
            continue
        try:
            task = get_lark_task(task_id)
            is_completed = task.get("status") == "done" or task.get("completed_at") not in (None, 0, "0", "")
            if is_completed:
                completed_at = task.get("completed_at")
                if completed_at and str(completed_at) != "0":
                    try:
                        completed_time = datetime.fromtimestamp(int(completed_at)).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        completed_time = now.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    completed_time = now.strftime("%Y-%m-%d %H:%M:%S")
                record_upsert(TRACKING_TABLE_ID, row["_record_id"], {
                    "完成状态": "已完成",
                    "完成时间": completed_time,
                })
                print(f"[已完成] {row.get('任务标题')} | {row.get('版本名称')} | {row.get('阶段名称')}")
        except Exception as e:
            print(f"[ERROR] task_id={task_id} {e}")


if __name__ == "__main__":
    main()

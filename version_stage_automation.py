import json
import subprocess
import sys
from datetime import datetime, date

BASE_TOKEN = "Mg9ZbeiFrah1xdsH31XcuDRanTf"
LARK_CLI = "lark-cli.cmd" if sys.platform == "win32" else "lark-cli"
GROUP_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/2d2db6c2-52bf-4d79-a922-9590cbafdbe3"
CHAT_ID = "oc_3353a9ce4d5020524053cdd8da6d45d3"

VERSION_TABLES = [
    {
        "version": "BP4+1",
        "table_id": "tbl6IACUxSTdQFeK",
    },
    {
        "version": "BP4+2",
        "table_id": "tblMkz8Jmk3dtXGW",
    },
    {
        "version": "BP5",
        "table_id": "tblNSS9myeq0hk7C",
    },
]
TASK_DETAIL_TABLE_ID = "tblzMARjnP3Ts7ZE"
TRACKING_TABLE_ID = "tblRWIWq1HDwknuq"


def run_cli(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    if not result.stdout.strip():
        raise RuntimeError(f"lark-cli returned empty stdout. stderr={result.stderr!r} args={args}")
    payload = json.loads(result.stdout)
    # lark-cli base 命令返回 {"ok": true, "data": ...}
    # lark-cli task 命令返回 {"code": 0, "data": ...}
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
    ])


def record_upsert(table_id, record_id, values):
    args = [
        LARK_CLI, "--as", "bot", "base", "+record-upsert",
        "--base-token", BASE_TOKEN,
        "--table-id", table_id,
        "--json", json.dumps(values, ensure_ascii=False),
    ]
    if record_id:
        args.extend(["--record-id", record_id])
    return run_cli(args)


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


def bold_text(text):
    return {"tag": "text", "text": text}


def mention_segment(user):
    return {
        "tag": "at",
        "user_id": user["id"],
        "user_name": user.get("name", ""),
    }


def group_tasks_by_owner(tasks):
    grouped = {}
    for task in tasks:
        task_name = task.get("任务名称") or ""
        for user in task.get("负责人") or []:
            user_id = user.get("id")
            if not user_id:
                continue
            if user_id not in grouped:
                grouped[user_id] = {"user": user, "tasks": []}
            grouped[user_id]["tasks"].append(task_name)
    return grouped.values()


def send_group_post(title, content):
    import urllib.request
    body = json.dumps({
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": content,
                }
            }
        },
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(GROUP_WEBHOOK, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8")


def create_lark_task(summary, user_id):
    due_ts = int(datetime.now().replace(hour=23, minute=59, second=0, microsecond=0).timestamp()) * 1000
    payload = {
        "summary": summary,
        "due": {"timestamp": str(due_ts)},
        "members": [{"id": user_id, "role": "assignee"}],
    }
    data = run_cli([
        LARK_CLI, "--as", "bot", "task", "tasks", "create",
        "--data", json.dumps(payload, ensure_ascii=False),
    ])
    task = data.get("task") or data
    return task.get("guid") or task.get("id") or task.get("task_id")


def load_task_details():
    rows = rows_by_fields(record_list(TASK_DETAIL_TABLE_ID))
    # 通知开关为 False 时跳过，null/True 都视为开启
    return [r for r in rows if r.get("通知开关") is not False and r.get("阶段名称") and r.get("通知类型")]


def matching_tasks(task_details, stage_name, notification_type):
    return [
        r for r in task_details
        if select_value(r.get("阶段名称")) == stage_name
        and select_value(r.get("通知类型")) == notification_type
        and r.get("任务名称")
        and r.get("负责人")
    ]


def parse_time(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000)
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def handle_stage_start(version, table_id, stage, tasks):
    title = f"卡拉彼丘移动端 {version}版本 {stage['阶段名称']} 已开始"
    content = [
        [{"tag": "text", "text": "请以下对应负责人关注相关阶段任务："}],
        [],
    ]
    for item in group_tasks_by_owner(tasks):
        content.append([mention_segment(item["user"])])
        for task_name in item["tasks"]:
            content.append([{"tag": "text", "text": task_name}])
        content.append([])
    send_group_post(title, content)
    record_upsert(table_id, stage["_record_id"], {"开始通知已发送": True})


def handle_stage_end(version, table_id, stage, tasks):
    for task in tasks:
        for owner in task.get("负责人") or []:
            title = f"{stage['阶段名称']}准出标准任务：{task['任务名称']}"
            task_id = create_lark_task(title, owner["id"])
            record_upsert(TRACKING_TABLE_ID, None, {
                "任务标题": title,
                "版本名称": version,
                "阶段名称": stage["阶段名称"],
                "任务内容": task.get("任务内容") or task.get("任务名称"),
                "负责人": [{"id": owner["id"]}],
                "飞书任务ID": task_id or "",
                "完成状态": "待完成",
                "任务截止时间": datetime.now().strftime("%Y-%m-%d 23:59:00"),
                "来源阶段记录ID": stage["_record_id"],
                "来源任务记录ID": task["_record_id"],
            })
    record_upsert(table_id, stage["_record_id"], {"结束任务已创建": True})


def main():
    now = datetime.now()
    task_details = load_task_details()
    for item in VERSION_TABLES:
        stages = rows_by_fields(record_list(item["table_id"]))
        for stage in stages:
            stage_name = stage.get("阶段名称")
            if not stage_name:
                continue
            start_time = parse_time(stage.get("开始日期"))
            end_time = parse_time(stage.get("结束日期"))
            if start_time and start_time <= now and stage.get("开始通知已发送") is not True:
                tasks = matching_tasks(task_details, stage_name, "阶段开始")
                if tasks:
                    handle_stage_start(item["version"], item["table_id"], stage, tasks)
            if end_time and end_time <= now and stage.get("结束任务已创建") is not True:
                tasks = matching_tasks(task_details, stage_name, "阶段结束")
                if tasks:
                    handle_stage_end(item["version"], item["table_id"], stage, tasks)


if __name__ == "__main__":
    main()

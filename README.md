# 版本周期自动化通知系统

基于飞书多维表格 + GitHub Actions，实现版本各阶段的自动通知和待办任务创建，无需本地服务器持续运行。

---

## 功能概述

| 触发时机 | 执行动作 |
|----------|----------|
| 阶段开始时间到达 | 在指定群发送富文本消息，@每位负责人并列出其对应任务 |
| 阶段结束时间到达 | 为每位负责人创建飞书待办任务，并记录到追踪表 |
| 每 5 分钟轮询一次 | 同步飞书任务完成状态回追踪表 |

---

## 多维表格结构

### Base Token
```
Mg9ZbeiFrah1xdsH31XcuDRanTf
```

### 表结构说明

#### 版本周期表（每个版本一张，如 BP4+1、BP4+2、BP5）
| 字段 | 类型 | 说明 |
|------|------|------|
| 阶段名称 | 文本 | 如「需求测试阶段」 |
| 开始日期 | 日期时间 | 阶段开始时间 |
| 结束日期 | 日期时间 | 阶段结束时间 |
| 开始通知已发送 | 勾选框 | 系统自动填写，防止重复通知 |
| 结束任务已创建 | 勾选框 | 系统自动填写，防止重复创建 |

#### 任务详情表（`tblzMARjnP3Ts7ZE`）
| 字段 | 类型 | 说明 |
|------|------|------|
| 任务名称 | 文本 | 任务描述 |
| 阶段名称 | 单选 | 与版本周期表中的阶段名称对应 |
| 通知类型 | 单选 | 「阶段开始」或「阶段结束」 |
| 负责人 | 人员 | 该任务的负责人 |
| 通知开关 | 勾选框 | 取消勾选可临时禁用某条任务 |

#### 阶段准出任务追踪表（`tblRWIWq1HDwknuq`）
系统自动写入，记录每个阶段结束时创建的飞书任务及其完成状态。

---

## 日常使用

### 修改阶段时间
直接在对应版本周期表里修改「开始日期」或「结束日期」即可。

**注意**：如果该阶段的「开始通知已发送」或「结束任务已创建」已经打勾（说明已触发过），修改时间后不会重复触发。若需要重新触发，手动取消勾选对应字段即可。

### 新增/修改任务详情
在任务详情表（`tblzMARjnP3Ts7ZE`）中增删改行，下次运行时自动生效，无需改代码。

---

## 新增版本周期表

每次开始新版本（如 BP5+1）时，按以下步骤操作：

### 第一步：在多维表格中新建版本周期表

1. 打开多维表格，点击左下角「+」新建表格
2. 表格命名为版本名称（如「BP5+1版本周期表」）
3. 添加以下字段：
   - `阶段名称`（文本）
   - `开始日期`（日期，格式：年-月-日 时:分:秒）
   - `结束日期`（日期，格式：年-月-日 时:分:秒）
   - `开始通知已发送`（勾选框）
   - `结束任务已创建`（勾选框）
4. 录入各阶段数据

### 第二步：获取新表的 table_id

在浏览器地址栏中找到 URL，其中 `tbl` 开头的字符串即为 table_id：
```
https://xxx.feishu.cn/base/Mg9ZbeiFrah1xdsH31XcuDRanTf?table=tblXXXXXXXXXX&view=...
                                                                  ^^^^^^^^^^^^^^
                                                                  这就是 table_id
```

### 第三步：更新脚本

打开 `version_stage_automation.py`，在 `VERSION_TABLES` 列表中添加新版本：

```python
VERSION_TABLES = [
    {"version": "BP4+1", "table_id": "tbl6IACUxSTdQFeK"},
    {"version": "BP4+2", "table_id": "tblMkz8Jmk3dtXGW"},
    {"version": "BP5",   "table_id": "tblNSS9myeq0hk7C"},
    {"version": "BP5+1", "table_id": "tblXXXXXXXXXX"},  # 新增这行
]
```

### 第四步：推送到 GitHub

```powershell
cd "f:\Claude test\模型"
git add version_stage_automation.py
git commit -m "Add BP5+1 version table"
git push
```

推送后 GitHub Actions 会在下一个 5 分钟周期自动使用新配置。

---

## 系统架构

```
GitHub Actions (每5分钟)
        │
        ├─ version_stage_automation.py
        │       │
        │       ├─ 读取版本周期表（各版本阶段时间）
        │       ├─ 读取任务详情表（通知内容和负责人）
        │       ├─ 阶段开始 → 发送群消息（Webhook）
        │       └─ 阶段结束 → 创建飞书任务 + 写入追踪表
        │
        └─ sync_task_status.py
                │
                ├─ 读取追踪表中「待完成」的任务
                └─ 查询飞书任务状态 → 已完成则更新追踪表
```

### 认证方式
- **Base 读写**：lark-cli bot 身份（app_id + app_secret，存储在 GitHub Secrets）
- **群消息**：Webhook 直接发送，无需认证
- **飞书任务**：lark-cli bot 身份

### GitHub Secrets 配置
| Secret 名称 | 说明 |
|-------------|------|
| `LARK_APP_ID` | 飞书应用 App ID：`cli_a95dd9b10c389cc2` |
| `LARK_APP_SECRET` | 飞书应用 App Secret |

---

## 常见问题

**Q：阶段时间到了但没收到通知？**
- 检查版本周期表中「开始通知已发送」是否已勾选（若已勾选说明已触发过）
- 检查任务详情表中对应阶段是否有「通知类型=阶段开始」且「通知开关」未关闭的记录
- 查看 GitHub Actions 运行日志：`https://github.com/don-wu/lark-automation/actions`

**Q：如何临时暂停某个阶段的通知？**
在任务详情表中将对应行的「通知开关」取消勾选即可。

**Q：GitHub Actions 最多延迟多久？**
调度间隔为 5 分钟，GitHub 在高负载时可能额外延迟几分钟，正常情况误差在 10 分钟内。

**Q：如何手动触发一次执行？**
打开 `https://github.com/don-wu/lark-automation/actions`，点击 **Version Stage Automation** → **Run workflow**。

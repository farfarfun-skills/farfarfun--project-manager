#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import html
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


STATUSES = "todo,in_progress,in_review,blocked,done,cancelled"
OPEN_STATUSES = ("todo", "in_progress", "in_review", "blocked")
DAILY_TITLE_RE = re.compile(r"^任务巡查(\d{4}-\d{2}-\d{2})$")
INSPECTION_TITLE_RE = re.compile(r"^任务巡查\d{4}-\d{2}(?:-\d{2})?$")


def unwrap_list(payload: object) -> list[dict]:
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    if isinstance(payload, dict):
        for key in ("issues", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
            if isinstance(value, dict):
                try:
                    return unwrap_list(value)
                except ValueError:
                    pass
    raise ValueError("Paperclip issue list response has no issue array")


def unwrap_issue(payload: object) -> dict:
    if isinstance(payload, dict) and payload.get("id"):
        return payload
    if isinstance(payload, dict):
        for key in ("issue", "data"):
            value = payload.get(key)
            if isinstance(value, dict) and value.get("id"):
                return value
    raise ValueError("Paperclip issue response has no issue object")


class PaperclipClient:
    def __init__(self, base_url: str, run_id: str | None, token: str | None, timeout: int):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Paperclip base URL must be an absolute http(s) URL")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id
        self.token = token
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict | None = None) -> object:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            if not self.run_id:
                raise ValueError("a Paperclip run ID is required for mutating requests")
            headers.update({
                "Content-Type": "application/json",
                "X-Paperclip-Run-Id": self.run_id,
            })
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(2000).decode("utf-8", errors="replace")
            raise RuntimeError(f"Paperclip {method} {path} failed ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Paperclip {method} {path} failed: {exc.reason}") from exc
        return json.loads(raw.decode("utf-8")) if raw else {}

    def list_issues(self, company_id: str) -> list[dict]:
        company = urllib.parse.quote(company_id, safe="")
        query = urllib.parse.urlencode({"status": STATUSES})
        return unwrap_list(self.request("GET", f"/api/companies/{company}/issues?{query}"))

    def get_issue(self, issue_id: str) -> dict:
        issue = urllib.parse.quote(issue_id, safe="")
        return unwrap_issue(self.request("GET", f"/api/issues/{issue}"))

    def create_issue(self, company_id: str, body: dict) -> dict:
        company = urllib.parse.quote(company_id, safe="")
        return unwrap_issue(self.request("POST", f"/api/companies/{company}/issues", body))

    def update_issue(self, issue_id: str, body: dict) -> dict:
        issue = urllib.parse.quote(issue_id, safe="")
        return unwrap_issue(self.request("PATCH", f"/api/issues/{issue}", body))


def issue_id(issue: dict) -> str:
    value = issue.get("id")
    if not isinstance(value, str) or not value:
        raise ValueError("Paperclip issue is missing id")
    return value


def issue_sort_key(issue: dict) -> tuple[str, str]:
    return (str(issue.get("createdAt") or "9999"), issue_id(issue))


def select_month(issues: list[dict], goal_id: str, target_date: date) -> tuple[dict | None, list[str]]:
    title = f"任务巡查{target_date:%Y-%m}"
    matches = sorted(
        (item for item in issues if item.get("title") == title and item.get("goalId") == goal_id),
        key=issue_sort_key,
    )
    return (matches[0] if matches else None, [issue_id(item) for item in matches[1:]])


def select_daily(
    issues: list[dict], goal_id: str, target_date: date, monthly_id: str
) -> tuple[dict | None, list[str]]:
    title = f"任务巡查{target_date:%Y-%m-%d}"
    matches = [item for item in issues if item.get("title") == title and item.get("goalId") == goal_id]
    matches.sort(key=lambda item: (item.get("parentId") != monthly_id, *issue_sort_key(item)))
    return (matches[0] if matches else None, [issue_id(item) for item in matches[1:]])


def patch_changed(client, issue: dict, expected: dict) -> dict:
    changes = {key: value for key, value in expected.items() if issue.get(key) != value}
    return client.update_issue(issue_id(issue), changes) if changes else issue


def issue_date(issue: dict) -> date | None:
    title = issue.get("title")
    match = DAILY_TITLE_RE.fullmatch(title) if isinstance(title, str) else None
    try:
        return date.fromisoformat(match.group(1)) if match else None
    except ValueError:
        return None


def issue_reference(issue: dict) -> str:
    value = issue.get("identifier") or issue.get("key") or issue_id(issue)
    return str(value)


def assignee_identity(issue: dict) -> tuple[str | None, str]:
    value = issue.get("assigneeAgentId")
    agent_id = value if isinstance(value, str) and value else None
    if agent_id is None:
        return None, "未分配"
    nested = issue.get("assigneeAgent")
    candidates = [
        issue.get("assigneeAgentName"),
        nested.get("name") if isinstance(nested, dict) else None,
    ]
    name = next((item for item in candidates if isinstance(item, str) and item.strip()), agent_id)
    return agent_id, name.strip()


def blocker_ids(issue: dict) -> list[str]:
    values = issue.get("blockedByIssueIds")
    if isinstance(values, list):
        return sorted({str(item) for item in values if item})
    values = issue.get("blockedBy")
    if not isinstance(values, list):
        return []
    return sorted({issue_id(item) for item in values if isinstance(item, dict) and item.get("id")})


def markdown_cell(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
    return html.escape(text, quote=False) or "-"


def render_report_markdown(report: dict) -> str:
    task_dimension = report["taskDimension"]
    agent_dimension = report["agentDimension"]
    counts = task_dimension["statusCounts"]
    top = agent_dimension["topAgent"]
    top_text = "无已分配 Agent"
    if top:
        top_text = f"{markdown_cell(top['name'])} (`{markdown_cell(top['id'])}`)，{top['total']} 项"
    lines = [
        "## 任务维度",
        "",
        f"- 未完成任务：{task_dimension['total']} 项",
        "- 状态分布：" + " / ".join(f"`{status}` {counts[status]}" for status in OPEN_STATUSES),
        "",
        "| 任务 | 标题 | 状态 | Agent | Blocker | 叶子 | 下游 |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
    ]
    if task_dimension["tasks"]:
        for task in task_dimension["tasks"]:
            agent = task["agentName"]
            if task["agentId"] and task["agentName"] != task["agentId"]:
                agent = f"{task['agentName']} ({task['agentId']})"
            blockers = "<br>".join(markdown_cell(item) for item in task["blockers"]) or "-"
            lines.append(
                f"| {markdown_cell(task['reference'])} | {markdown_cell(task['title'])} | "
                f"{markdown_cell(task['status'])} | {markdown_cell(agent)} | {markdown_cell(blockers)} | "
                f"{'是' if task['isLeaf'] else '否'} | {task['downstreamCount']} |"
            )
    else:
        lines.append("| - | 当前无未完成任务 | - | - | - | - | 0 |")
    lines.extend([
        "",
        "## Agent 维度",
        "",
        f"- 未完成任务最多：{top_text}",
        "",
        "| 排名 | Agent | 未完成 | todo | in_progress | in_review | blocked | 任务 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    if agent_dimension["agents"]:
        for agent in agent_dimension["agents"]:
            label = agent["name"]
            if agent["id"] and agent["name"] != agent["id"]:
                label = f"{agent['name']} ({agent['id']})"
            lines.append(
                f"| {agent['rank'] or '-'} | {markdown_cell(label)} | {agent['total']} | "
                f"{agent['statusCounts']['todo']} | {agent['statusCounts']['in_progress']} | "
                f"{agent['statusCounts']['in_review']} | {agent['statusCounts']['blocked']} | "
                f"{'<br>'.join(markdown_cell(item) for item in agent['taskReferences']) or '-'} |"
            )
    else:
        lines.append("| - | 当前无 Agent 未完成任务 | 0 | 0 | 0 | 0 | 0 | - |")
    return "\n".join(lines) + "\n"


def build_inspection_report(issues: list[dict], generated_at: datetime) -> dict:
    open_issues = [
        issue for issue in issues
        if issue.get("status") in OPEN_STATUSES
        and not (isinstance(issue.get("title"), str) and INSPECTION_TITLE_RE.fullmatch(issue["title"]))
    ]
    issue_by_id = {issue_id(issue): issue for issue in open_issues}
    tasks = []
    workloads: dict[str | None, dict] = {}
    status_counts = Counter()
    for issue in open_issues:
        status = issue.get("status")
        title = issue.get("title")
        agent_id, agent_name = assignee_identity(issue)
        unresolved_ids = [value for value in blocker_ids(issue) if value in issue_by_id]
        task = {
            "id": issue_id(issue),
            "reference": issue_reference(issue),
            "title": str(title or ""),
            "status": status,
            "agentId": agent_id,
            "agentName": agent_name,
            "blockerIds": unresolved_ids,
            "blockers": [issue_reference(issue_by_id[value]) for value in unresolved_ids],
        }
        tasks.append(task)
        status_counts[status] += 1
        workload = workloads.setdefault(agent_id, {
            "id": agent_id,
            "names": set(),
            "statusCounts": Counter(),
            "taskReferences": [],
        })
        workload["names"].add(agent_name)
        workload["statusCounts"][status] += 1
        workload["taskReferences"].append(task["reference"])

    task_by_id = {task["id"]: task for task in tasks}
    dependents = {task["id"]: set() for task in tasks}
    dependency_edges = []
    for task in tasks:
        for blocked_by_id in task["blockerIds"]:
            dependents[blocked_by_id].add(task["id"])
            dependency_edges.append({
                "blockedTaskId": task["id"],
                "blockedTaskReference": task["reference"],
                "blockerTaskId": blocked_by_id,
                "blockerTaskReference": task_by_id[blocked_by_id]["reference"],
            })
    # ponytail: per-task graph walks fit inspection-sized sets; cache reachability if task counts become large.
    for task in tasks:
        seen = {task["id"]}
        pending = list(dependents[task["id"]])
        while pending:
            dependent_id = pending.pop()
            if dependent_id in seen:
                continue
            seen.add(dependent_id)
            pending.extend(dependents[dependent_id] - seen)
        task["isLeaf"] = not task["blockerIds"]
        task["downstreamCount"] = len(seen) - 1

    tasks.sort(key=lambda item: (OPEN_STATUSES.index(item["status"]), item["reference"], item["id"]))
    impact_key = lambda item: (-item["downstreamCount"], item["reference"], item["id"])
    leaf_top_20 = [
        {key: task[key] for key in ("id", "reference", "status", "agentId", "downstreamCount")}
        for task in sorted((item for item in tasks if item["isLeaf"]), key=impact_key)[:20]
    ]
    blocked_top_10 = [
        {key: task[key] for key in ("id", "reference", "agentId", "blockerIds", "downstreamCount")}
        for task in sorted((item for item in tasks if item["status"] == "blocked"), key=impact_key)[:10]
    ]
    agents = []
    for workload in workloads.values():
        counts = {status: workload["statusCounts"][status] for status in OPEN_STATUSES}
        names = sorted(workload["names"], key=lambda item: (item == workload["id"], item.casefold(), item))
        agents.append({
            "id": workload["id"],
            "name": names[0],
            "total": sum(counts.values()),
            "statusCounts": counts,
            "taskReferences": sorted(workload["taskReferences"]),
        })
    agents.sort(key=lambda item: (item["id"] is None, -item["total"], item["name"].casefold(), item["id"] or ""))
    rank = 0
    for agent in agents:
        if agent["id"] is not None:
            rank += 1
            agent["rank"] = rank
        else:
            agent["rank"] = None
    top_agent = next((agent for agent in agents if agent["id"] is not None), None)
    report = {
        "generatedAt": generated_at.isoformat(timespec="seconds"),
        "taskDimension": {
            "total": len(tasks),
            "statusCounts": {status: status_counts[status] for status in OPEN_STATUSES},
            "tasks": tasks,
            "dependencyEdges": sorted(dependency_edges, key=lambda item: (item["blockedTaskReference"], item["blockerTaskReference"])),
            "leafTop20": leaf_top_20,
            "blockedTop10": blocked_top_10,
        },
        "agentDimension": {"topAgent": top_agent, "agents": agents},
    }
    report["markdown"] = render_report_markdown(report)
    return report


def complete_past_days(client, issues: list[dict], goal_id: str, today: date) -> list[str]:
    completed = []
    dates = sorted({value for item in issues if item.get("goalId") == goal_id and (value := issue_date(item)) and value < today})
    for target_date in dates:
        month, _ = select_month(issues, goal_id, target_date)
        if month is None:
            continue
        daily, _ = select_daily(issues, goal_id, target_date, issue_id(month))
        if daily is not None and daily.get("status") not in {"done", "cancelled"}:
            client.update_issue(issue_id(daily), {"status": "done"})
            completed.append(issue_id(daily))
    return completed


def ensure_tasks(
    client,
    company_id: str,
    goal_id: str,
    coordinator_agent_id: str,
    cto_agent_id: str,
    target_date: date,
) -> dict:
    issues = client.list_issues(company_id)
    completed_past = complete_past_days(client, issues, goal_id, target_date)

    month, duplicate_month_ids = select_month(issues, goal_id, target_date)
    month_created = month is None
    if month is None:
        month = client.create_issue(company_id, {
            "title": f"任务巡查{target_date:%Y-%m}",
            "description": f"{target_date:%Y-%m} 任务巡查容器。每日结果写入子任务。",
            "status": "done",
            "assigneeAgentId": coordinator_agent_id,
            "goalId": goal_id,
        })
        issues = client.list_issues(company_id)
        visible, duplicate_month_ids = select_month(issues, goal_id, target_date)
        month = visible or month
    month = patch_changed(client, month, {
        "status": "done",
        "assigneeAgentId": coordinator_agent_id,
        "goalId": goal_id,
    })
    monthly_id = issue_id(month)

    issues = client.list_issues(company_id)
    daily, duplicate_daily_ids = select_daily(issues, goal_id, target_date, monthly_id)
    daily_created = daily is None
    if daily is None:
        daily = client.create_issue(company_id, {
            "title": f"任务巡查{target_date:%Y-%m-%d}",
            "description": f"{target_date:%Y-%m-%d} 任务巡查记录。",
            "status": "todo",
            "assigneeAgentId": cto_agent_id,
            "parentId": monthly_id,
            "goalId": goal_id,
        })
        issues = client.list_issues(company_id)
        visible, duplicate_daily_ids = select_daily(issues, goal_id, target_date, monthly_id)
        daily = visible or daily
    daily = patch_changed(client, daily, {
        "assigneeAgentId": cto_agent_id,
        "parentId": monthly_id,
        "goalId": goal_id,
    })
    daily_id = issue_id(daily)
    return {
        "date": target_date.isoformat(),
        "monthlyTaskId": monthly_id,
        "monthlyTaskCreated": month_created,
        "duplicateMonthlyTaskIds": duplicate_month_ids,
        "dailyTaskId": daily_id,
        "reportTaskId": daily_id,
        "dailyTaskCreated": daily_created,
        "duplicateDailyTaskIds": duplicate_daily_ids,
        "completedPastDailyTaskIds": completed_past,
    }


def complete_day(client, company_id: str, goal_id: str, target_date: date) -> dict:
    issues = client.list_issues(company_id)
    month, duplicate_month_ids = select_month(issues, goal_id, target_date)
    if month is None:
        raise ValueError("canonical monthly task does not exist")
    daily, duplicate_daily_ids = select_daily(issues, goal_id, target_date, issue_id(month))
    if daily is None:
        raise ValueError("canonical daily task does not exist")
    if daily.get("status") not in {"done", "cancelled"}:
        daily = client.update_issue(issue_id(daily), {"status": "done"})
    return {
        "date": target_date.isoformat(),
        "monthlyTaskId": issue_id(month),
        "dailyTaskId": issue_id(daily),
        "status": daily.get("status"),
        "duplicateMonthlyTaskIds": duplicate_month_ids,
        "duplicateDailyTaskIds": duplicate_daily_ids,
    }


def guard_target(client, company_id: str, goal_id: str, target_date: date, target_id: str) -> dict:
    issues = client.list_issues(company_id)
    month, _ = select_month(issues, goal_id, target_date)
    if month is None:
        raise ValueError("canonical monthly task does not exist")
    monthly_id = issue_id(month)
    daily, _ = select_daily(issues, goal_id, target_date, monthly_id)
    if daily is None:
        raise ValueError("canonical daily task does not exist")
    expected_id = issue_id(daily)
    target = client.get_issue(target_id)
    expected_title = f"任务巡查{target_date:%Y-%m-%d}"
    if target_id != expected_id or target_id == monthly_id:
        raise ValueError(f"report target must be canonical daily task {expected_id}, got {target_id}")
    if target.get("title") != expected_title or target.get("parentId") != monthly_id:
        raise ValueError("report target title or parentId does not match the canonical daily task")
    return {"reportTaskId": expected_id, "monthlyTaskId": monthly_id, "valid": True}


@contextmanager
def resolver_lock(base_url: str, company_id: str, goal_id: str, target_date: date):
    root = Path(tempfile.gettempdir()) / f"paperclip-task-coordinator-{os.getuid()}"
    root.mkdir(mode=0o700, exist_ok=True)
    key = hashlib.sha256(f"{base_url}|{company_id}|{goal_id}|{target_date}".encode()).hexdigest()
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(root / f"{key}.lock", flags, 0o600)
    # ponytail: this serializes same-host runs; use a server-side unique key if coordinators span hosts.
    with os.fdopen(descriptor, "a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def env(name: str) -> str | None:
    return os.getenv(name) or None


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", default=env("PAPERCLIP_API_URL"), help="Paperclip API base URL; defaults to PAPERCLIP_API_URL")
    parser.add_argument("--company-id", default=env("PAPERCLIP_COMPANY_ID"))
    parser.add_argument("--goal-id", default=env("PAPERCLIP_GOAL_ID"))
    parser.add_argument("--run-id", default=env("PAPERCLIP_RUN_ID"))
    parser.add_argument("--token-env", default="PAPERCLIP_API_TOKEN", help="Environment variable containing an optional bearer token")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--date", help="Inspection date in YYYY-MM-DD; defaults to the company timezone date")
    parser.add_argument("--timezone", default=env("PAPERCLIP_TIMEZONE") or "Asia/Shanghai")


def required(parser: argparse.ArgumentParser, args: argparse.Namespace, *names: str) -> None:
    missing = [name.replace("_", "-") for name in names if not getattr(args, name)]
    if missing:
        parser.error(f"missing required arguments or environment values: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage canonical Paperclip inspection tasks and render deterministic reports.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure = subparsers.add_parser("ensure", help="Get or create canonical monthly and daily tasks")
    add_connection_arguments(ensure)
    ensure.add_argument("--coordinator-agent-id", default=env("PAPERCLIP_AGENT_ID"))
    ensure.add_argument("--cto-agent-id", default=env("PAPERCLIP_CTO_AGENT_ID"), help="Current company CTO agent ID; canonical daily tasks are always assigned to it")

    complete = subparsers.add_parser("complete-day", help="Mark the canonical daily task done")
    add_connection_arguments(complete)

    guard = subparsers.add_parser("guard-target", help="Verify a report target is the canonical daily task")
    add_connection_arguments(guard)
    guard.add_argument("--target-id", required=True)

    report = subparsers.add_parser("report", help="Render unfinished work by task and agent")
    add_connection_arguments(report)
    report.add_argument("--format", choices=("json", "markdown"), default="json")

    args = parser.parse_args()
    required(parser, args, "base_url", "company_id")
    if args.command != "report":
        required(parser, args, "goal_id")
    if args.command in {"ensure", "complete-day"}:
        required(parser, args, "run_id")
    if args.command == "ensure":
        required(parser, args, "coordinator_agent_id", "cto_agent_id")
    try:
        current_time = datetime.now(ZoneInfo(args.timezone))
        target_date = date.fromisoformat(args.date) if args.date else current_time.date()
    except (ValueError, KeyError) as exc:
        parser.error(f"invalid date or timezone: {exc}")
    client = PaperclipClient(args.base_url, args.run_id, env(args.token_env), args.timeout)

    try:
        if args.command == "guard-target":
            result = guard_target(client, args.company_id, args.goal_id, target_date, args.target_id)
        elif args.command == "report":
            result = build_inspection_report(client.list_issues(args.company_id), current_time)
        else:
            with resolver_lock(args.base_url, args.company_id, args.goal_id, target_date):
                if args.command == "ensure":
                    result = ensure_tasks(
                        client, args.company_id, args.goal_id,
                        args.coordinator_agent_id, args.cto_agent_id, target_date,
                    )
                else:
                    result = complete_day(client, args.company_id, args.goal_id, target_date)
    except (RuntimeError, ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.command == "report" and args.format == "markdown":
        print(result["markdown"], end="")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

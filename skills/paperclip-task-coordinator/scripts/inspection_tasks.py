#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


STATUSES = "todo,in_progress,in_review,blocked,done,cancelled"
DAILY_TITLE_RE = re.compile(r"^任务巡查(\d{4}-\d{2}-\d{2})$")


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
    parser = argparse.ArgumentParser(description="Resolve canonical Paperclip monthly and daily inspection tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure = subparsers.add_parser("ensure", help="Get or create canonical monthly and daily tasks")
    add_connection_arguments(ensure)
    ensure.add_argument("--coordinator-agent-id", default=env("PAPERCLIP_AGENT_ID"))
    ensure.add_argument("--cto-agent-id", default=env("PAPERCLIP_CTO_AGENT_ID"))

    complete = subparsers.add_parser("complete-day", help="Mark the canonical daily task done")
    add_connection_arguments(complete)

    guard = subparsers.add_parser("guard-target", help="Verify a report target is the canonical daily task")
    add_connection_arguments(guard)
    guard.add_argument("--target-id", required=True)

    args = parser.parse_args()
    required(parser, args, "base_url", "company_id", "goal_id")
    if args.command != "guard-target":
        required(parser, args, "run_id")
    if args.command == "ensure":
        required(parser, args, "coordinator_agent_id", "cto_agent_id")
    try:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(args.timezone)).date()
    except (ValueError, KeyError) as exc:
        parser.error(f"invalid date or timezone: {exc}")
    client = PaperclipClient(args.base_url, args.run_id, env(args.token_env), args.timeout)

    try:
        if args.command == "guard-target":
            result = guard_target(client, args.company_id, args.goal_id, target_date, args.target_id)
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

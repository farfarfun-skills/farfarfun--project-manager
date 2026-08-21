import sys
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from inspection_tasks import PaperclipClient, build_inspection_report, complete_day, ensure_tasks, guard_target, main


class FakeClient:
    def __init__(self, issues=None):
        self.issues = [dict(item) for item in issues or []]
        self.created = []
        self.updated = []

    def list_issues(self, _company_id):
        return [dict(item) for item in self.issues]

    def get_issue(self, target_id):
        return dict(next(item for item in self.issues if item["id"] == target_id))

    def create_issue(self, _company_id, body):
        issue = {"id": f"I-{len(self.issues) + 1}", "createdAt": f"2026-08-21T00:00:{len(self.issues):02d}Z", **body}
        self.issues.append(issue)
        self.created.append(dict(issue))
        return dict(issue)

    def update_issue(self, target_id, body):
        issue = next(item for item in self.issues if item["id"] == target_id)
        issue.update(body)
        self.updated.append((target_id, dict(body)))
        return dict(issue)


def month(issue_id="M-1", status="done"):
    return {
        "id": issue_id, "title": "任务巡查2026-08", "goalId": "G-1",
        "assigneeAgentId": "COORD", "status": status, "createdAt": "2026-08-01T00:00:00Z",
    }


def daily(issue_id="D-1", parent_id="M-1", day="21", status="todo", created="00"):
    return {
        "id": issue_id, "title": f"任务巡查2026-08-{day}", "goalId": "G-1",
        "parentId": parent_id, "assigneeAgentId": "CTO", "status": status,
        "createdAt": f"2026-08-{day}T00:00:{created}Z",
    }


class InspectionTaskTests(unittest.TestCase):
    def test_http_issue_query_is_company_wide(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b"[]"

        with patch("urllib.request.urlopen", return_value=Response()) as opened:
            PaperclipClient("https://paperclip.example", "RUN-1", None, 5).list_issues("C-1")

        url = opened.call_args.args[0].full_url
        self.assertIn("status=", url)
        self.assertNotIn("assigneeAgentId", url)

    def test_ensure_reuses_cto_owned_daily_task(self):
        client = FakeClient([month(), daily()])

        result = ensure_tasks(client, "C-1", "G-1", "COORD", "CTO", date(2026, 8, 21))

        self.assertEqual("D-1", result["reportTaskId"])
        self.assertEqual([], client.created)

    def test_ensure_creates_each_task_once_and_completes_month(self):
        client = FakeClient()

        first = ensure_tasks(client, "C-1", "G-1", "COORD", "CTO", date(2026, 8, 21))
        second = ensure_tasks(client, "C-1", "G-1", "COORD", "CTO", date(2026, 8, 21))

        self.assertEqual(2, len(client.created))
        self.assertEqual(first["monthlyTaskId"], second["monthlyTaskId"])
        self.assertEqual(first["dailyTaskId"], second["dailyTaskId"])
        self.assertEqual("done", client.get_issue(first["monthlyTaskId"])["status"])

    def test_duplicate_daily_tasks_use_oldest_valid_parent(self):
        client = FakeClient([
            month(),
            daily("D-WRONG", parent_id="OTHER", created="00"),
            daily("D-CANONICAL", created="01"),
            daily("D-DUPLICATE", created="02"),
        ])

        result = ensure_tasks(client, "C-1", "G-1", "COORD", "CTO", date(2026, 8, 21))

        self.assertEqual("D-CANONICAL", result["dailyTaskId"])
        self.assertEqual(["D-DUPLICATE", "D-WRONG"], result["duplicateDailyTaskIds"])
        self.assertEqual([], client.created)

    def test_next_day_and_explicit_completion_mark_daily_done(self):
        client = FakeClient([month(), daily("D-20", day="20"), daily("D-21")])

        result = ensure_tasks(client, "C-1", "G-1", "COORD", "CTO", date(2026, 8, 21))
        completed = complete_day(client, "C-1", "G-1", date(2026, 8, 21))

        self.assertEqual(["D-20"], result["completedPastDailyTaskIds"])
        self.assertEqual("done", completed["status"])

    def test_guard_rejects_monthly_task(self):
        client = FakeClient([month(), daily()])

        with self.assertRaisesRegex(ValueError, "canonical daily task"):
            guard_target(client, "C-1", "G-1", date(2026, 8, 21), "M-1")

    def test_report_ranks_agents_and_renders_both_dimensions(self):
        issues = [
            {"id": "I-1", "identifier": "APP-1", "title": "实现登录 <script>", "status": "todo", "assigneeAgentId": "A-1", "assigneeAgentName": "前端"},
            {"id": "I-2", "identifier": "APP-2", "title": "修复登录", "status": "blocked", "assigneeAgentId": "A-1", "assigneeAgentName": "前端", "blockedByIssueIds": ["I-3"]},
            {"id": "I-3", "identifier": "APP-3", "title": "接口测试", "status": "in_progress", "assigneeAgentId": "A-2", "assigneeAgent": {"name": "测试"}},
            {"id": "I-4", "identifier": "APP-4", "title": "待分配", "status": "todo"},
            {"id": "I-5", "identifier": "APP-5", "title": "已完成", "status": "done", "assigneeAgentId": "A-2"},
            daily(),
        ]

        report = build_inspection_report(issues, datetime(2026, 8, 21, 8, tzinfo=timezone.utc))

        self.assertEqual(4, report["taskDimension"]["total"])
        self.assertEqual("A-1", report["agentDimension"]["topAgent"]["id"])
        self.assertEqual(2, report["agentDimension"]["topAgent"]["total"])
        self.assertEqual(["A-1", "A-2", None], [item["id"] for item in report["agentDimension"]["agents"]])
        self.assertEqual("I-3", report["taskDimension"]["leafTop20"][0]["id"])
        self.assertEqual(1, report["taskDimension"]["leafTop20"][0]["downstreamCount"])
        self.assertEqual("I-2", report["taskDimension"]["blockedTop10"][0]["id"])
        self.assertIn("## 任务维度", report["markdown"])
        self.assertIn("## Agent 维度", report["markdown"])
        self.assertIn("未完成任务最多：前端 (`A-1`)，2 项", report["markdown"])
        self.assertIn("实现登录 &lt;script&gt;", report["markdown"])

    def test_report_cli_is_read_only_and_needs_no_goal_or_run_id(self):
        output = StringIO()
        argv = ["inspection_tasks.py", "report", "--base-url", "https://paperclip.example", "--company-id", "C-1", "--format", "markdown"]
        with patch.object(sys, "argv", argv), patch.object(PaperclipClient, "list_issues", return_value=[]), redirect_stdout(output):
            self.assertEqual(0, main())

        self.assertIn("## 任务维度", output.getvalue())
        self.assertIn("## Agent 维度", output.getvalue())


if __name__ == "__main__":
    unittest.main()

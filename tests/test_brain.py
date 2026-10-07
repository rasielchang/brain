import copy
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from workbrain.clients import API, task_tree
from workbrain.collect import collect
from workbrain.config import DEFAULT, credential, validate
from workbrain.reports import render
from workbrain.runner import generate
from workbrain.storage import BrainError, atomic_write, run_lock
from workbrain.cli import SOURCE, initialize, main, refresh, report


class Response:
    def __init__(self, body, headers=None):
        self.body = json.dumps(body).encode()
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.body


class Opener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class APITests(unittest.TestCase):
    def api(self, responses, provider="asana"):
        opener = Opener(responses)
        return API("https://api.example.com/v1", "synthetic", provider, opener, sleep=lambda _: None), opener

    def test_asana_follows_all_offsets(self):
        api, opener = self.api([Response({"data": [{"gid": "a"}], "next_page": {"offset": "next+cursor"}}), Response({"data": [{"gid": "b"}], "next_page": None})])
        self.assertEqual([t["gid"] for t in api.all("/tasks")], ["a", "b"])
        self.assertIn("offset=next%2Bcursor", opener.requests[1].full_url)
        self.assertTrue(all(r.method == "GET" for r in opener.requests))

    def test_gitlab_uses_link_header(self):
        api, opener = self.api([Response([1], {"Link": '<https://api.example.com/v1/tasks?cursor=second>; rel="next"'}), Response([2])], "gitlab")
        self.assertEqual(api.all("/tasks"), [1, 2])
        self.assertEqual(opener.requests[1].full_url, "https://api.example.com/v1/tasks?cursor=second")

    def test_cross_origin_pagination_refused_before_auth_sent(self):
        api, opener = self.api([Response([1], {"Link": '<https://evil.example/tasks>; rel="next"'})], "gitlab")
        with self.assertRaises(BrainError):
            api.all("/tasks")
        self.assertEqual(len(opener.requests), 1)

    def test_cursor_cycle_rejected(self):
        api, _ = self.api([Response({"data": [1], "next_page": {"offset": "same"}})] * 3)
        with self.assertRaisesRegex(BrainError, "repeated"):
            api.all("/tasks")

    def test_second_page_failure_is_not_partial_success(self):
        failure = urllib.error.HTTPError("https://api.example.com", 403, "Forbidden", {}, io.BytesIO(b"secret body"))
        api, _ = self.api([Response({"data": [1], "next_page": {"offset": "next"}}), failure])
        with self.assertRaises(BrainError) as result:
            api.all("/tasks")
        self.assertIn("403", str(result.exception))
        self.assertNotIn("secret body", str(result.exception))

    def test_retry_only_bounded_transient_failure(self):
        failure = urllib.error.HTTPError("https://api.example.com", 429, "Limited", {"Retry-After": "0"}, None)
        api, opener = self.api([failure, Response({"data": []})])
        self.assertEqual(api.all("/tasks"), [])
        self.assertEqual(len(opener.requests), 2)

    def test_long_rate_limit_does_not_retry_early(self):
        failure = urllib.error.HTTPError("https://api.example.com", 429, "Limited", {"Retry-After": "90"}, None)
        api, opener = self.api([failure])
        with self.assertRaisesRegex(BrainError, "retry later"):
            api.all("/tasks")
        self.assertEqual(len(opener.requests), 1)

    def test_insecure_or_embedded_credential_base_rejected(self):
        for url in ("http://example.com", "https://user:secret@example.com/api", "https://example.com/api?token=x"):
            with self.subTest(url=url), self.assertRaises(BrainError):
                API(url, "test", "asana")

    def test_nested_and_multihomed_tasks_are_complete_and_unique(self):
        class Tree:
            def all(self, path, params):
                return {"/projects/p/tasks": [{"gid": "root", "num_subtasks": 1}, {"gid": "child", "num_subtasks": 1}],
                        "/tasks/root/subtasks": [{"gid": "child", "num_subtasks": 1}],
                        "/tasks/child/subtasks": [{"gid": "leaf", "num_subtasks": 0}]}[path]
            def one(self, path, params):
                return {"gid": "root", "num_subtasks": 1}
        self.assertEqual({t["gid"] for t in task_tree(Tree(), "p", ["root"])}, {"root", "child", "leaf"})


class ConfigTests(unittest.TestCase):
    def test_credentials_do_not_fall_back(self):
        with patch.dict(os.environ, {"UNRELATED_TOKEN": "not-the-right-token"}, clear=True):
            with self.assertRaises(BrainError):
                credential({"env": "MISSING"})

    def test_credential_sources_are_exclusive(self):
        with self.assertRaises(BrainError):
            credential({"env": "A", "command": ["echo", "B"]})

    def test_helper_runs_without_shell(self):
        result = credential({"command": [sys.executable, "-c", "print('synthetic-value')"]})
        self.assertEqual(result, "synthetic-value")

    def test_config_rejects_unknown_focus_project(self):
        config = copy.deepcopy(DEFAULT)
        config["weekly_focus"] = {"1": ["missing"]}
        with self.assertRaises(BrainError):
            validate(config)

    def test_paused_projects_do_not_connect(self):
        config = copy.deepcopy(DEFAULT)
        config["projects"] = [{"id": "p", "name": "Paused", "status": "paused", "gitlab_projects": [1], "asana_project": "a"}]
        snapshot = collect(config, factory=lambda *a: self.fail("Paused project must not connect"))
        self.assertEqual(snapshot["projects"], [])

    def test_owner_assignments_under_paused_ancestors_are_excluded(self):
        config = copy.deepcopy(DEFAULT)
        config["owner"] = {"asana_user": "user", "asana_workspace": "ws"}
        config["providers"] = {"asana": {"credential": {"env": "TEST_CREDENTIAL"}}}
        config["projects"] = [{"id": "p", "name": "Paused", "status": "paused", "asana_roots": ["root"]}]
        class Tasks:
            def all(self, *args):
                return [{"gid": "leaf", "completed": False, "parent": {"gid": "middle"}}, {"gid": "active", "completed": False}]
            def one(self, path, params):
                return {"/tasks/middle": {"gid": "middle", "parent": {"gid": "root"}}, "/tasks/root": {"gid": "root"}}[path]
        with patch.dict(os.environ, {"TEST_CREDENTIAL": "synthetic"}):
            snapshot = collect(config, factory=lambda *a: Tasks())
        self.assertEqual([t["gid"] for t in snapshot["assignments"]], ["active"])


class ReportsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((SOURCE / "examples/demo.json").read_text())

    def test_all_focus_projects_and_routine_remain_visible(self):
        config = self.fixture["config"]
        config["weekly_focus"]["1"] = ["atlas", "studio"]
        report_text = render(self.fixture["snapshot"], config)
        self.assertEqual(report_text.count("today's focus"), 2)
        self.assertIn("Write: today's completion not reported", report_text)
        self.assertIn("acceptance is still pending", report_text)

    def test_holidays_do_not_schedule_focus_or_routines(self):
        self.fixture["config"]["non_working_dates"] = ["2026-01-12"]
        result = render(self.fixture["snapshot"], self.fixture["config"])
        self.assertNotIn("today's focus", result)
        self.assertNotIn("Write: today's", result)
        self.assertIn("No work is scheduled", result)

    def test_current_week_count_does_not_use_last_week(self):
        self.fixture["snapshot"]["projects"][0]["repos"][0]["commits"][0]["committed_date"] = "2026-01-11T07:00:00Z"
        result = render(self.fixture["snapshot"], self.fixture["config"])
        self.assertNotIn("This week: 1 recorded", result)

    def test_progress_week_uses_configured_timezone(self):
        self.fixture["config"]["timezone"] = "Asia/Taipei"
        self.fixture["snapshot"]["projects"][0]["repos"][0]["commits"][0]["committed_date"] = "2026-01-11T18:00:00Z"
        result = render(self.fixture["snapshot"], self.fixture["config"])
        self.assertIn("This week: 1 recorded", result)

    def test_source_report_does_not_overwrite_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "daily/2026-01-12.md"
            atomic_write(path, "User decision: wait for customer.")
            report(root, self.fixture["config"], self.fixture["snapshot"], "today")
            self.assertEqual(path.read_text(), "User decision: wait for customer.")
            self.assertTrue((root / "daily/2026-01-12.source.md").exists())


class ReliabilityTests(unittest.TestCase):
    def test_collection_failure_preserves_previous_snapshot_and_portfolio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_write(root / ".brain/snapshot.json", "previous snapshot")
            atomic_write(root / "PORTFOLIO.md", "previous portfolio")
            with patch("workbrain.cli.collect", side_effect=BrainError("failed")):
                with self.assertRaises(BrainError):
                    refresh(root, DEFAULT)
            self.assertEqual((root / ".brain/snapshot.json").read_text(), "previous snapshot")
            self.assertEqual((root / "PORTFOLIO.md").read_text(), "previous portfolio")

    def test_lock_serializes_runs_and_releases_after_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            with run_lock(folder):
                with self.assertRaises(BrainError):
                    with run_lock(folder):
                        self.fail("Second lock acquired")
            with run_lock(folder):
                pass

    def test_initialization_preserves_existing_personal_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root)
            atomic_write(root / "reminders.md", "A personal reminder")
            initialize(root)
            self.assertEqual((root / "reminders.md").read_text(), "A personal reminder")
            self.assertEqual(json.loads((root / ".brain/config.json").read_text())["projects"], [])

    def test_private_files_have_restricted_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "private.json"
            atomic_write(path, "private")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_stale_snapshot_not_presented_as_today(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root)
            atomic_write(root / ".brain/snapshot.json", '{"collected_at":"2000-01-01T00:00:00Z"}')
            self.assertEqual(main(["--root", str(root), "brief"]), 1)

    def test_failed_agent_keeps_old_report_and_strips_connector_token(self):
        fixture = json.loads((SOURCE / "examples/demo.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".brain").mkdir()
            output = root / "daily.md"
            output.write_text("prior decision")
            class Failed:
                returncode = 1
                def __init__(self, command, **kwargs):
                    self.env = kwargs["env"]
                    if "ASANA_TOKEN" in self.env:
                        raise AssertionError("Connector token exposed")
                def communicate(self, prompt, timeout):
                    return ("error", "hidden diagnostic")
            with patch.dict(os.environ, {"ASANA_TOKEN": "synthetic-secret"}), patch("workbrain.runner.subprocess.Popen", Failed):
                with self.assertRaises(BrainError):
                    generate(root, SOURCE, fixture["snapshot"], fixture["config"], "today", output, "codex")
            self.assertEqual(output.read_text(), "prior decision")

    def test_successful_agent_publishes_report(self):
        fixture = json.loads((SOURCE / "examples/demo.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".brain").mkdir()
            output = root / "daily.md"
            expected = "# Today · 2026-01-12\n\n" + "Synthetic evidence; acceptance is unknown.\n" * 8
            class Success:
                returncode = 0
                def __init__(self, command, **kwargs):
                    path = command[command.index("--output-last-message") + 1]
                    Path(path).write_text(expected)
                def communicate(self, prompt, timeout):
                    return ("", "")
            with patch("workbrain.runner.subprocess.Popen", Success):
                generate(root, SOURCE, fixture["snapshot"], fixture["config"], "today", output, "codex")
            self.assertEqual(output.read_text(), expected)

    def test_agent_timeout_terminates_group_and_preserves_report(self):
        fixture = json.loads((SOURCE / "examples/demo.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".brain").mkdir()
            output = root / "daily.md"
            output.write_text("previous")
            class Slow:
                returncode = -9
                pid = 999999
                def __init__(self, *args, **kwargs):
                    pass
                def communicate(self, *args, **kwargs):
                    if "timeout" in kwargs:
                        raise subprocess.TimeoutExpired("fake-agent", 1)
                    return ("", "")
            with patch("workbrain.runner.subprocess.Popen", Slow), patch("workbrain.runner.os.killpg") as kill:
                with self.assertRaisesRegex(BrainError, "timed out"):
                    generate(root, SOURCE, fixture["snapshot"], fixture["config"], "today", output, "codex", timeout=1)
                kill.assert_called_once()
            self.assertEqual(output.read_text(), "previous")


class ReleaseTests(unittest.TestCase):
    def test_release_checker_detects_private_files_and_tokens(self):
        spec = importlib.util.spec_from_file_location("release_check", SOURCE / "bin/check-release.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn("private workspace file", module.violations(".brain/config.json", b"{}"))
        fake = ("ghp_" + "x" * 30).encode()
        self.assertIn("GitHub token", module.violations("example.txt", fake))
        self.assertEqual(module.violations("examples/config.json", b'{"credential":{"env":"ASANA_TOKEN"}}'), [])

    def test_skills_have_discoverable_frontmatter(self):
        for name in ("today", "weekly", "radar", "schedule", "inbox"):
            skill = (SOURCE / ".agents/skills" / name / "SKILL.md").read_text()
            self.assertTrue(skill.startswith("---\nname: " + name + "\n"))
            self.assertIn("description:", skill.split("---", 2)[1])
            self.assertNotIn("TODO", skill)


if __name__ == "__main__":
    unittest.main()

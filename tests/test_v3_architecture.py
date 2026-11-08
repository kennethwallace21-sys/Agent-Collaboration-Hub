"""Acceptance tests for ACH v3 architectural upgrades (Slices 1-3).

Exercises cursor completeness, project isolation/policies, session & model
provenance, transactional outbox + SSE event stream, delivery state machine,
owner approval authority, inert historical import, and multi-round reviews.
All state is disposable and isolated from external delivery or consultations.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

os.environ["COLLAB_DISABLE_EXTERNAL_DELIVERY"] = "1"
os.environ["COLLAB_ALERTS_AUTOSTART"] = "0"
os.environ["COLLAB_ALLOW_CONSULTS"] = "0"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_source(name: str, path: Path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


class V3ArchitectureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="collab-v3-arch-")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.env_patch = patch.dict(os.environ, {
            "COLLAB_WORKSPACE": str(self.workspace),
            "COLLAB_DISABLE_EXTERNAL_DELIVERY": "1",
            "COLLAB_ALERTS_AUTOSTART": "0",
            "COLLAB_ALLOW_CONSULTS": "0",
            "COLLAB_HEADLESS": "0",
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        self.hub = load_source("v3_hub", ROOT / "collab.py")
        self.alerts = load_source("v3_alerts", ROOT / "alerts.py")
        self.mod_patch = patch.dict(sys.modules, {"collab": self.hub, "alerts": self.alerts})
        self.mod_patch.start()
        self.addCleanup(self.mod_patch.stop)

        self.mcp = load_source("v3_mcp", ROOT / "mcp_server.py")
        self.advisory = load_source("v3_advisory", ROOT / "advisory.py")
        self.adv_patch = patch.object(self.advisory, "post_collab_message")
        self.adv_patch.start()
        self.addCleanup(self.adv_patch.stop)
        self.hub.init_db()

    def call(self, name, arguments=None):
        """Call an MCP tool through the real dispatch path and return its payload."""
        result = self.mcp.call_tool({"name": name, "arguments": arguments or {}})
        self.assertFalse(result["isError"], result["content"][0]["text"])
        return json.loads(result["content"][0]["text"])

    def call_expecting_failure(self, name, arguments):
        result = self.mcp.call_tool({"name": name, "arguments": arguments})
        self.assertTrue(result["isError"], result["content"][0]["text"])
        return result["content"][0]["text"]

    def test_cursor_completeness_drains_backlog_without_skipping(self):
        for idx in range(1, 26):
            ch = "reviews" if idx % 2 == 0 else "general"
            self.hub.op_post("codex", f"Message #{idx}", channel=ch)

        seen_ids = []
        cursor = 0
        pages = 0
        while True:
            page = self.mcp.t_read(since=cursor, limit=10)
            pages += 1
            batch_ids = [m["id"] for m in page["messages"]]
            seen_ids.extend(batch_ids)
            self.assertEqual(page["latest_id"], page["next_since"])
            cursor = page["next_since"]
            if not page["has_more"]:
                break
        self.assertEqual(pages, 3)
        self.assertEqual(seen_ids, list(range(1, 26)))

        # Subsequent read at end of cursor returns empty and preserves cursor
        tail = self.mcp.t_read(since=cursor, limit=10)
        self.assertEqual(tail["messages"], [])
        self.assertEqual(tail["latest_id"], 25)

        # Filtered cursor traversal by channel never skips matching records
        review_ids = []
        rcursor = 0
        while True:
            rpage = self.mcp.t_read(channel="reviews", since=rcursor, limit=5)
            review_ids.extend(m["id"] for m in rpage["messages"])
            rcursor = rpage["next_since"]
            if not rpage["has_more"]:
                break
        self.assertEqual(review_ids, [i for i in range(1, 26) if i % 2 == 0])

    def test_first_class_projects_isolation_and_policies(self):
        va = self.hub.op_project_create(
            "virtual-assistant",
            "Virtual Assistant",
            repo_path=r"C:\dev\agents\fable\virtual-assistant",
            status="active",
            policy={"forbidden_paths": [r"D:\va"], "forbid_em_dash": True},
            shared_channels=["announcements"],
        )
        self.assertTrue(va["ok"])

        hcm = self.hub.op_project_create(
            "hcm",
            "HCM Platform",
            repo_path=r"C:\dev\agents\bedrock\hcm-platform",
            status="on_hold",
            hold_reason="Owner hold 2026-10-30; dev-hcm scaled to 0",
        )
        self.assertTrue(hcm["ok"])

        # Task creation on an ON_HOLD project is blocked by default
        blocked_task = self.hub.op_task_add("fable", "Run terragrunt", project_id="hcm")
        self.assertFalse(blocked_task["ok"])
        self.assertIn("ON HOLD", blocked_task["error"])

        # Forbidden path (D:\va) and em-dash policy enforced in virtual-assistant
        bad_post = self.hub.op_post("codex", r"Reading voice sample from D:\va\raw.wav", project_id="virtual-assistant")
        self.assertFalse(bad_post["ok"])
        self.assertIn("D:\\va", bad_post["error"])

        em_dash_post = self.hub.op_post("codex", "No em dash allowed \u2014 here", project_id="virtual-assistant")
        self.assertFalse(em_dash_post["ok"])
        self.assertIn("em dash", em_dash_post["error"])

        # Valid scoped posts and tasks stay isolated between projects
        self.hub.op_post("fable", "VA sprint update", channel="general", project_id="virtual-assistant")
        self.hub.op_post("fable", "Default board note", channel="general", project_id="default")
        self.hub.op_post("fable", "Cross-project notice", channel="announcements", project_id="default")

        va_msgs = self.mcp.t_read(project_id="virtual-assistant", limit=20)["messages"]
        self.assertEqual([m["content"] for m in va_msgs], ["VA sprint update", "Cross-project notice"])

        # Archive and restore preserve references
        self.hub.op_project_update("virtual-assistant", status="archived")
        archived_attempt = self.hub.op_post("fable", "While archived", project_id="virtual-assistant")
        self.assertFalse(archived_attempt["ok"])
        self.hub.op_project_update("virtual-assistant", status="active")
        restored_attempt = self.hub.op_post("fable", "After restore", project_id="virtual-assistant")
        self.assertTrue(restored_attempt["ok"])

    def test_concurrent_sessions_preserve_distinct_model_attribution(self):
        # Session A joins as gemini-3.8-flash (runtime_observed)
        self.mcp.t_join(
            agent_id="gemini",
            model="gemini-3.8-flash",
            surface="antigravity-win1",
            role="Reviewer",
            session_id="sess-win1",
            provider="google",
            runtime="antigravity-ide",
            model_provenance="runtime_observed",
            announce=False,
        )
        # Session B joins under the same agent seat with a different model
        self.mcp.t_join(
            agent_id="gemini",
            model="gemini-4-argon-high",
            surface="antigravity-win2",
            role="Implementer",
            session_id="sess-win2",
            provider="google",
            runtime="antigravity-ide",
            model_provenance="agent_declared",
            announce=False,
        )
        # Post from Session A must retain Session A's exact model & provenance
        post_a = self.mcp.t_post(
            sender="gemini",
            content="Reviewing from window 1",
            session_id="sess-win1",
        )
        post_b = self.mcp.t_post(
            sender="gemini",
            content="Implementing from window 2",
            session_id="sess-win2",
        )
        self.assertEqual(post_a["model"], "gemini-3.8-flash")
        self.assertEqual(post_a["model_provenance"], "runtime_observed")
        self.assertEqual(post_b["model"], "gemini-4-argon-high")
        self.assertEqual(post_b["model_provenance"], "agent_declared")

        roster = self.mcp.t_roster()
        gemini_entry = next(a for a in roster["agents"] if a["id"] == "gemini")
        self.assertEqual({s["session_id"] for s in gemini_entry["sessions"]}, {"sess-win1", "sess-win2"})

    def test_transactional_outbox_and_event_wait_wakeup(self):
        baseline = self.hub.op_read_events(since_seq=0)["latest_seq"]
        received = []

        def waiter():
            res = self.hub.wait_for_events(since_seq=baseline, timeout=5.0)
            received.append(res)

        thread = threading.Thread(target=waiter)
        thread.start()
        time.sleep(0.05)
        self.hub.op_post("fable", "Wake event test")
        thread.join(timeout=3.0)
        self.assertTrue(received)
        self.assertFalse(received[0]["timed_out"])
        self.assertTrue(any(ev["event_type"] == "message.created" for ev in received[0]["events"]))

    def test_delivery_state_machine_and_hook_crash_safety(self):
        res = self.alerts.notify("fable", "codex", "Please review T148")
        inbox_items = self.alerts.inbox("codex", mark_read=False)["alerts"]
        self.assertEqual(len(inbox_items), 1)
        alert_id = inbox_items[0]["id"]
        self.assertEqual(inbox_items[0]["delivery_state"], "queued")

        # Simulate broken stdout pipe in run_hook: alert must stay unread & queued
        class BrokenStdout:
            def write(self, _):
                raise BrokenPipeError("simulated host pipe failure")

            def flush(self):
                raise BrokenPipeError("simulated host pipe failure")

        with patch.object(sys, "stdin", io.StringIO("{}")), patch.object(sys, "stdout", BrokenStdout()):
            self.alerts.run_hook("codex", "codex", "SessionStart")

        still_unread = self.alerts.inbox("codex", mark_read=False)["alerts"]
        self.assertEqual(len(still_unread), 1)
        self.assertEqual(still_unread[0]["delivery_state"], "queued")

        # Bounded retries transition to failed after max_retries (3)
        self.assertFalse(self.alerts.record_delivery_attempt(alert_id, False, "try 1")["exhausted"])
        self.assertFalse(self.alerts.record_delivery_attempt(alert_id, False, "try 2")["exhausted"])
        final_try = self.alerts.record_delivery_attempt(alert_id, False, "try 3")
        self.assertTrue(final_try["exhausted"])
        self.assertEqual(final_try["delivery_state"], "failed")

        # Explicit state transitions (accepted -> in_progress -> completed)
        self.assertEqual(
            self.alerts.transition_alert(alert_id, "codex", "accepted", session_id="codex-s1")["alert"]["delivery_state"],
            "accepted",
        )
        self.assertEqual(
            self.alerts.transition_alert(alert_id, "codex", "in_progress")["alert"]["delivery_state"],
            "in_progress",
        )
        self.assertEqual(
            self.alerts.transition_alert(alert_id, "codex", "completed")["alert"]["delivery_state"],
            "completed",
        )

    def test_owner_control_prevents_peer_self_approval_and_replay(self):
        prop = self.hub.op_propose(
            "codex",
            "Cutover to ACH",
            "Switch authoritative board",
            artifact_ref="phase_2.md",
            artifact_revision="rev-1",
        )
        dec_id = prop["decision_id"]

        # Peer agent attempts to set status='approved' via t_vote
        vote_res = self.mcp.t_vote(dec_id, "claude", "approve", comment="LGTM", status="approved")
        self.assertTrue(vote_res["ok"])
        self.assertEqual(vote_res["peer_status"], "approved")
        self.assertEqual(vote_res["status"], "open")
        self.assertEqual(vote_res["owner_status"], "pending")
        self.assertTrue(vote_res["owner_approval_required"])

        # Agent without owner token cannot call op_owner_approve
        bad_auth = self.hub.op_owner_approve("decision", dec_id, "approve", owner_token="forged-token")
        self.assertFalse(bad_auth["ok"])

        # Owner approval with stale artifact_revision is rejected
        real_token = self.hub.get_owner_token()
        stale = self.hub.op_owner_approve(
            "decision",
            dec_id,
            "approve",
            owner_token=real_token,
            artifact_revision="rev-0-stale",
            nonce="nonce-1",
        )
        self.assertFalse(stale["ok"])
        self.assertIn("Stale approval", stale["error"])

        # Valid owner approval succeeds and binds nonce
        approved = self.hub.op_owner_approve(
            "decision",
            dec_id,
            "approve",
            owner_token=real_token,
            artifact_revision="rev-1",
            nonce="nonce-1",
        )
        self.assertTrue(approved["ok"])
        self.assertEqual(approved["status"], "approved")

        # Replaying the same nonce is rejected
        replay = self.hub.op_owner_approve(
            "decision",
            dec_id,
            "approve",
            owner_token=real_token,
            artifact_revision="rev-1",
            nonce="nonce-1",
        )
        self.assertFalse(replay["ok"])
        self.assertIn("nonce", replay["error"])

    def test_inert_historical_import_triggers_zero_alerts_and_is_idempotent(self):
        bundle = {
            "projects": [{"id": "virtual-assistant", "name": "Virtual Assistant", "status": "active"}],
            "agents": [{"id": "fable", "model": "claude-opus-5-5", "role": "Orchestrator"}],
            "tasks": [
                {
                    "external_id": "T148",
                    "project_id": "virtual-assistant",
                    "title": "VA Product Docs",
                    "status": "assigned",
                    "owner": "codex",
                    "created_by": "fable",
                }
            ],
            "messages": [
                {
                    "external_id": "20261031T164529Z-fable",
                    "project_id": "virtual-assistant",
                    "channel": "general",
                    "sender": "fable",
                    "content": "@codex @gemini @opus-bedrock historical broadcast",
                }
            ],
            "lessons": [
                {
                    "id": "L004",
                    "title": "Orchestrator lock verification",
                    "rule_text": "Verify active lock session before task dispatch.",
                }
            ],
        }
        first = self.hub.op_import_history(bundle)
        self.assertTrue(first["ok"])
        self.assertEqual(first["imported"]["tasks"], 1)
        self.assertEqual(first["imported"]["messages"], 1)
        self.assertEqual(first["imported"]["lessons"], 1)

        # Scanner must generate zero alerts for imported historical mentions/tasks
        created_alerts = self.alerts.scan()
        self.assertEqual(created_alerts, 0)
        self.assertEqual(self.alerts.inbox("codex", mark_read=False)["alerts"], [])
        self.assertEqual(self.alerts.inbox("gemini", mark_read=False)["alerts"], [])

        # Second import of the same bundle is idempotent (0 duplicates)
        second = self.hub.op_import_history(bundle)
        self.assertEqual(second["imported"]["tasks"], 0)
        self.assertEqual(second["imported"]["messages"], 0)

    def test_task_states_and_multi_round_independent_reviews(self):
        # Assigning a task to an unavailable agent starts in 'assigned', not 'in_progress'
        added = self.mcp.t_task_add("fable", "Implement Audio Pipeline", assign="opus-bedrock")
        self.assertEqual(added["status"], "assigned")
        tid = added["task_id"]

        # Transition through accepted -> in_progress -> waiting_user -> review -> done
        for st in ("accepted", "in_progress", "waiting_user", "review", "done"):
            upd = self.mcp.t_task_update(tid, "opus-bedrock", status=st, deliverable="shared/audio.md" if st == "review" else "")
            self.assertEqual(upd["status"], st)

        # First-class multi-round reviews preserve Round 1 when Round 2 is submitted
        r1 = self.hub.op_review_submit(
            "shared/audio.md",
            "gemini",
            "Round 1 finding: buffer underrun at line 42",
            task_id=tid,
            artifact_revision="v1",
            author_agent="opus-bedrock",
            author_model="us.anthropic.claude-opus-5-5",
            reviewer_model="gemini-4-argon-high",
            verdict="changes_requested",
            preserved_disagreements="Buffer size tradeoff",
        )
        self.assertTrue(r1["ok"])
        self.assertEqual(r1["round_number"], 1)
        self.assertTrue(r1["is_independent_model"])

        r2 = self.hub.op_review_submit(
            "shared/audio.md",
            "gemini",
            "Round 2 verification: buffer fixed in v2",
            task_id=tid,
            artifact_revision="v2",
            author_agent="opus-bedrock",
            author_model="us.anthropic.claude-opus-5-5",
            reviewer_model="gemini-4-argon-high",
            verdict="approved",
        )
        self.assertTrue(r2["ok"])
        self.assertEqual(r2["round_number"], 2)

        # Advisory panel also preserves Round 1 history when Round 2 is submitted
        with io.StringIO():
            self.advisory.cmd_request("Review Architecture", "Context", "human")
            self.advisory.cmd_respond(1, "codex", "Round 1 critique", artifact_revision="v1")
            self.advisory.cmd_respond(1, "codex", "Round 2 follow-up", artifact_revision="v2")
        store = self.advisory.load_store()
        codex_resp = store["sessions"][0]["responses"]["codex"]
        self.assertEqual(codex_resp["round"], 2)
        self.assertEqual(len(codex_resp["history"]), 2)
        self.assertEqual(codex_resp["history"][0]["advice"], "Round 1 critique")
        self.assertEqual(codex_resp["history"][1]["advice"], "Round 2 follow-up")


    def test_mcp_exposes_v3_project_review_event_and_lock_surfaces(self):
        """Every v3 surface must be reachable through the MCP tool dispatch."""
        expected = {
            "collab_project_list", "collab_project_create", "collab_project_update",
            "collab_project_assign", "collab_review_list", "collab_review_submit",
            "collab_review_respond", "collab_events", "collab_events_wait",
            "collab_orchestrator_lock", "collab_owner_approve",
        }
        self.assertTrue(expected.issubset(set(self.mcp.TOOLS)), sorted(expected - set(self.mcp.TOOLS)))
        for name in sorted(expected):
            schema = self.mcp.TOOLS[name]["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"], name)
            self.assertTrue(schema["properties"], name)

        created = self.call("collab_project_create", {
            "project_id": "virtual-assistant", "name": "Virtual Assistant", "created_by": "fable",
            "status": "active", "policy": {"forbid_em_dash": True}, "shared_channels": ["announcements"],
        })
        self.assertEqual((created["project_id"], created["status"]), ("virtual-assistant", "active"))
        assigned = self.call("collab_project_assign", {
            "project_id": "virtual-assistant", "agent_id": "codex", "role": "implementer",
        })
        self.assertEqual(assigned["role"], "implementer")
        listed = self.call("collab_project_list", {})
        self.assertEqual([p["id"] for p in listed["projects"]], ["default", "virtual-assistant"])
        virtual_assistant = next(p for p in listed["projects"] if p["id"] == "virtual-assistant")
        self.assertEqual([m["agent_id"] for m in virtual_assistant["members"]], ["codex"])

        # An on-hold project refuses new work even through the MCP task tool.
        held = self.call("collab_project_update", {
            "project_id": "virtual-assistant", "actor": "human", "status": "on_hold",
            "hold_reason": "Owner hold",
        })
        self.assertEqual(held["status"], "on_hold")
        self.assertIn("ON HOLD", self.call_expecting_failure("collab_task_add", {
            "created_by": "fable", "title": "Blocked work", "project_id": "virtual-assistant",
        }))

        # An omitted field keeps its previous value, and archived projects stay hidden by default.
        archived = self.call("collab_project_update", {
            "project_id": "virtual-assistant", "actor": "human", "status": "archived",
        })
        self.assertEqual(archived["status"], "archived")
        self.assertEqual([p["id"] for p in self.call("collab_project_list", {})["projects"]], ["default"])
        archived_rows = self.call("collab_project_list", {"include_archived": True})["projects"]
        self.assertEqual([p["id"] for p in archived_rows], ["default", "virtual-assistant"])
        self.assertEqual(
            next(p for p in archived_rows if p["id"] == "virtual-assistant")["hold_reason"], "Owner hold"
        )

        # Reviews keep one round per submission, so Round 1 survives Round 2.
        first = self.call("collab_review_submit", {
            "artifact_ref": "shared/audio.md", "reviewer_agent": "gemini",
            "evidence": "Round 1 finding: buffer underrun", "artifact_revision": "v1",
            "author_agent": "opus-bedrock", "verdict": "changes_requested", "model": "gemini-4-argon-high",
        })
        self.assertEqual(first["round_number"], 1)
        self.assertTrue(first["is_independent_model"])
        second = self.call("collab_review_submit", {
            "artifact_ref": "shared/audio.md", "reviewer_agent": "gemini",
            "evidence": "Round 2 verification: fixed", "artifact_revision": "v2",
            "author_agent": "opus-bedrock", "verdict": "approved", "model": "gemini-4-argon-high",
        })
        self.assertEqual(second["round_number"], 2)
        rounds = self.call("collab_review_list", {"artifact_ref": "shared/audio.md"})["reviews"]
        self.assertEqual([r["round_number"] for r in rounds], [1, 2])
        self.assertEqual([r["verdict"] for r in rounds], ["changes_requested", "approved"])
        responded = self.call("collab_review_respond", {
            "review_id": first["review_id"], "actor": "opus-bedrock",
            "author_response": "Fixed in v2", "resolution": "confirmed", "status": "resolved",
        })
        self.assertEqual(responded["status"], "resolved")

        # The event stream is durable and cursor-based.
        events = self.call("collab_events", {"since_seq": 0})
        self.assertIn("review.submitted", [e["event_type"] for e in events["events"]])
        self.assertEqual(self.call("collab_events", {"since_seq": events["next_seq"]})["events"], [])
        idle = self.call("collab_events_wait", {"since_seq": events["next_seq"], "timeout_seconds": 0})
        self.assertEqual(idle["events"], [])
        self.assertTrue(idle["timed_out"])

        # One orchestrator dispatches a project's work at a time.
        acquired = self.call("collab_orchestrator_lock", {
            "project_id": "virtual-assistant", "agent_id": "fable", "session_id": "sess-fable",
        })
        self.assertEqual(acquired["holder_agent"], "fable")
        self.assertIn("already held", self.call_expecting_failure("collab_orchestrator_lock", {
            "project_id": "virtual-assistant", "agent_id": "codex", "session_id": "sess-codex",
        }))
        self.assertEqual(
            self.call("collab_orchestrator_lock", {
                "project_id": "virtual-assistant", "action": "status",
            })["lock"]["holder_agent"],
            "fable",
        )
        self.assertTrue(self.call("collab_orchestrator_lock", {
            "project_id": "virtual-assistant", "agent_id": "fable", "session_id": "sess-fable",
            "action": "release",
        })["released"])


    def test_mcp_owner_approval_requires_the_workspace_token(self):
        """A peer vote never approves a decision; only the owner token can."""
        decision_id = self.call("collab_propose", {
            "agent_id": "codex", "topic": "Cutover", "proposal": "Switch authoritative board",
            "artifact_ref": "phase_2.md", "artifact_revision": "rev-1",
        })["decision_id"]

        peer = self.call("collab_vote", {
            "decision_id": decision_id, "agent_id": "claude", "vote": "approve", "status": "approved",
        })
        self.assertEqual(peer["peer_status"], "approved")
        self.assertEqual(peer["status"], "open")
        self.assertTrue(peer["owner_approval_required"])

        self.assertIn("owner authorization", self.call_expecting_failure("collab_owner_approve", {
            "entity_type": "decision", "entity_id": decision_id, "action": "approve",
            "owner_token": "f" * 40,
        }))
        token = self.hub.get_owner_token()
        self.assertIn("Stale approval", self.call_expecting_failure("collab_owner_approve", {
            "entity_type": "decision", "entity_id": decision_id, "action": "approve",
            "owner_token": token, "artifact_revision": "rev-0-stale", "nonce": "mcp-stale-1",
        }))
        approved = self.call("collab_owner_approve", {
            "entity_type": "decision", "entity_id": decision_id, "action": "approve",
            "owner_token": token, "artifact_revision": "rev-1", "nonce": "mcp-ok-1",
        })
        self.assertEqual(approved["status"], "approved")
        self.assertIn("nonce", self.call_expecting_failure("collab_owner_approve", {
            "entity_type": "decision", "entity_id": decision_id, "action": "approve",
            "owner_token": token, "artifact_revision": "rev-1", "nonce": "mcp-ok-1",
        }))

    def test_mcp_v3_schemas_reject_unsupported_arguments(self):
        """The dispatch layer rejects unknown arguments, bad enums, and empty tokens."""
        self.assertIn("unknown argument", self.call_expecting_failure("collab_project_list", {"project": "x"}))
        self.assertIn("must be one of", self.call_expecting_failure("collab_project_create", {
            "project_id": "p", "name": "P", "created_by": "fable", "status": "paused",
        }))
        self.assertIn("must be one of", self.call_expecting_failure("collab_review_submit", {
            "artifact_ref": "shared/a.md", "reviewer_agent": "gemini", "evidence": "e", "verdict": "lgtm",
        }))
        self.assertIn("must be one of", self.call_expecting_failure("collab_owner_approve", {
            "entity_type": "project", "entity_id": 1, "action": "approve", "owner_token": "f" * 40,
        }))
        self.assertIn("must not be empty", self.call_expecting_failure("collab_owner_approve", {
            "entity_type": "decision", "entity_id": 1, "action": "approve", "owner_token": "short",
        }))
        self.assertIn("'owner_token' is required", self.call_expecting_failure("collab_owner_approve", {
            "entity_type": "decision", "entity_id": 1, "action": "approve",
        }))

    def test_dashboard_live_chat_ui_and_migration_script_rehearsal(self):
        """Dashboard UI contains zero em dashes and migration script imports inertly."""
        dashboard_text = (ROOT / "assets" / "dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("\u2014", dashboard_text)
        self.assertIn("<title>AI Agent Collab Space</title>", dashboard_text)
        self.assertIn('id="projects-list"', dashboard_text)
        self.assertIn('id="messages-list"', dashboard_text)
        self.assertIn('id="tasks-list"', dashboard_text)

        mig_mod = load_source("migrate_agents_home", ROOT / "scripts" / "migrate_agents_home.py")
        synth_dir = self.workspace / "synth_agents_home"
        (synth_dir / "tasks").mkdir(parents=True)
        (synth_dir / "board").mkdir(parents=True)
        (synth_dir / "audits").mkdir(parents=True)
        (synth_dir / "roster.json").write_text(
            json.dumps({"orchestrator": "fable", "agents": [{"id": "fable", "role": "orchestrator"}]}),
            encoding="utf-8",
        )
        (synth_dir / "tasks" / "T001.md").write_text(
            "---\nid: T001\nproject: angie\ntitle: Initial Task\nlane: codex\nstatus: DELIVERED\n---\nBody\n",
            encoding="utf-8",
        )
        (synth_dir / "board" / "20261031T000000Z-fable-test.md").write_text(
            "---\nid: 20261031T000000Z-fable-test\nfrom: fable\nto: all\ntype: note\nre: T001\nsubject: Hello\nposted: 2026-10-31T00:00:00Z\n---\n@codex @gemini hello\n",
            encoding="utf-8",
        )
        (synth_dir / "LESSONS.md").write_text(
            "| ID | Date | Source | Lesson | Enforcement | Status |\n|---|---|---|---|---|---|\n| L001 | 2026-10-15 | Audit | Rule 1 | Script | active |\n",
            encoding="utf-8",
        )
        (synth_dir / "audits" / "2026-10-15.md").write_text("# Audit 1\nPassed.\n", encoding="utf-8")

        bundle = mig_mod.build_migration_bundle(synth_dir)
        first = self.hub.op_import_history(bundle)
        self.assertTrue(first["ok"])
        self.assertEqual(first["imported"]["projects"], 5)
        self.assertEqual(first["imported"]["tasks"], 1)
        self.assertEqual(first["imported"]["messages"], 1)
        self.assertEqual(first["imported"]["decisions"], 1)
        self.assertEqual(first["imported"]["lessons"], 1)
        self.assertEqual(self.alerts.scan(), 0)

        second = self.hub.op_import_history(bundle)
        self.assertTrue(all(v == 0 for v in second["imported"].values()))

    def test_migrator_requires_an_explicit_source_and_carries_no_personal_path(self):
        """The migration source must be named, and the shipped source names nobody's folder."""
        mig_mod = load_source("migrate_agents_home_required", ROOT / "scripts" / "migrate_agents_home.py")
        from contextlib import redirect_stderr

        for argv in ([], ["--verify-rehearsal"]):
            with self.assertRaises(SystemExit, msg=f"{argv} should require --source"):
                with redirect_stderr(io.StringIO()):
                    mig_mod.main(argv)

        text = (ROOT / "scripts" / "migrate_agents_home.py").read_text(encoding="utf-8")
        self.assertNotIn("Users\\kenne", text)
        self.assertNotIn("Company_Website_live", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


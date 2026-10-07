from __future__ import annotations

import json
import time
from typing import Any

from brain.planner import Planner
from tools.registry import ToolRegistry
from tools.executor_v4 import ToolExecutorV4
from memory.engine import LongTermMemory
from knowledge.store import KnowledgeStore


class AgentRunner:
    """Universal KAREEM_AGENT runner.

    Compatible with the existing app interface: `AgentRunner(workspace, max_steps).run(text)`.
    """

    def __init__(self, workspace="workspace", max_steps=60):
        self.workspace = workspace
        self.max_steps = int(max_steps)
        self.planner = Planner()
        self.registry = ToolRegistry(workspace)
        self.executor = ToolExecutorV4(self.registry)
        self.memory = LongTermMemory()
        self.knowledge = KnowledgeStore()
        self.history: list[dict[str, Any]] = []

    def _print_step(self, step, plan):
        print("\n" + "=" * 70)
        print(f"KAREEM_AGENT V4 | THINK / STEP {step}/{self.max_steps}")
        print("=" * 70)
        print("PLAN:")
        print(json.dumps(plan, ensure_ascii=False, indent=2))

    def _observe(self, tool, action, args, result):
        item = {"ts": time.time(), "role": "tool", "tool": tool, "action": action, "arguments": args, "result": result}
        self.history.append(item)
        return item

    def _recent_knowledge(self, user_message):
        # Keep retrieval cheap; a local FTS lookup is enough for first-pass context.
        try:
            return self.knowledge.search(user_message, limit=6)
        except Exception:
            return []

    def _should_auto_remember(self, user_message, result):
        if not isinstance(result, dict) or not result.get("success", False):
            return False
        return any(k in user_message.lower() for k in ["اتذكر", "افتكر", "احفظ", "remember", "تعلم", "اتعلم", "learn"])

    def run(self, user_message):
        self.history = [{"role": "user", "content": user_message}]
        for step in range(1, self.max_steps + 1):
            try:
                plan = self.planner.plan(
                    user_message=user_message,
                    history=self.history,
                    tools=self.registry.describe(),
                    memory=self.memory.search(user_message, limit=6),
                    knowledge=self._recent_knowledge(user_message),
                )
            except Exception as exc:
                return {"success": False, "error": f"Planner failure: {exc}"}
            self._print_step(step, plan)

            if plan.get("type") == "chat":
                content = str(plan.get("content") or "").strip()
                # Reject premature empty/fake completions when there is history with failures.
                failed = any(isinstance(h.get("result"), dict) and h["result"].get("success") is False for h in self.history if h.get("role") == "tool")
                if content and not (failed and any(w in content.lower() for w in ["تم", "نجح", "done", "success"])):
                    return content
                self.history.append({"role": "assistant", "content": content, "note": "chat_before_verified_completion"})
                continue

            tool = str(plan.get("tool") or "").strip()
            action = str(plan.get("action") or "").strip()
            args = plan.get("arguments") or {}
            if not tool or not action:
                self.history.append({"role": "system", "content": "Invalid tool call; choose a valid capability."})
                continue

            print(f"\nACT {tool}.{action}")
            print(json.dumps(args, ensure_ascii=False, indent=2))
            result = self.executor.execute(tool, action, **args)
            print("\nOBSERVE:")
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            obs = self._observe(tool, action, args, result)

            if self._should_auto_remember(user_message, result):
                try:
                    self.memory.remember(
                        f"User goal: {user_message}\nSuccessful result: {json.dumps(result, ensure_ascii=False, default=str)[:6000]}",
                        metadata={"tool": tool, "action": action},
                    )
                except Exception:
                    pass

            # Successful learning task: persist a compact memory hint.
            if tool == "learning" and action == "learn_site" and isinstance(result, dict) and result.get("success"):
                try:
                    self.memory.remember(
                        f"Learned public site {result.get('start_url')} with {result.get('pages_learned')} pages.",
                        metadata={"kind": "learning", "url": result.get("start_url")},
                    )
                except Exception:
                    pass

            # Never repeat an identical failed call immediately.
            if isinstance(result, dict) and not result.get("success", True):
                self.history.append({"role": "system", "content": "The last tool call failed. Diagnose the exact error and choose a different/repaired action."})

            # Loop breaker: the same successful action repeated without a state-changing observation
            # is usually a planner loop. Tell the next planning turn to switch strategy or verify.
            signature = json.dumps({"tool": tool, "action": action, "arguments": args}, ensure_ascii=False, sort_keys=True)
            same_count = 0
            for h in reversed(self.history):
                if h.get("role") != "tool":
                    continue
                sig = json.dumps({"tool": h.get("tool"), "action": h.get("action"), "arguments": h.get("arguments") or {}}, ensure_ascii=False, sort_keys=True)
                if sig == signature:
                    same_count += 1
                else:
                    break
            if same_count >= 2:
                self.history.append({"role": "system", "content": "LOOP GUARD: this exact successful action has already run twice consecutively. Do NOT repeat it. Inspect/verify state, perform a different action, or return the final answer only if the user's goal is proven complete."})

        return {"success": False, "error": f"Task stopped after {self.max_steps} adaptive steps.", "history": self.history[-12:]}

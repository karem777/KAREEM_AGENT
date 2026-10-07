# KAREEM_AGENT V2 — researched architecture

## Why the current loop keeps breaking

The latest run showed a recurring class of failures:

1. The analytical graph is correct.
2. The browser executes correctly for earlier steps.
3. The planner is called again and the model is allowed to reinterpret the already-decided graph.
4. The model can switch browser work into `web.search`, invent aliases such as `execute_browser_action`, or emit arguments (`new_tab`) that the installed implementation does not accept.
5. A failed action is then re-proposed, consuming all 24 steps.

The core architectural fix is **deterministic-first execution**: once the goal graph identifies the next ready step, the planner should not be allowed to invent a different tool or skip to another step. The LLM remains available for ambiguous arguments, repair, and genuinely open-ended reasoning.

## Patterns adopted from open-source agents

### OpenHands
OpenHands describes an event-driven reasoning/action loop with explicit tool orchestration, context management, and security validation. Its execution model is action → observation, with confirmation for higher-risk actions. We adopt the same separation: planning, execution, observation, and security are separate boundaries.

Source: `OpenHands/docs/sdk/arch/agent.mdx`

### Browser Use
Browser Use exposes explicit loop detection, planning stall handling, max failures, step timeouts, structured browser actions, and page fingerprints. We adopt the principle that repeated identical actions are a runtime failure signal, not a reason to ask the same model question again.

### Playwright MCP
Playwright MCP bases browser interaction on accessibility snapshots and stable element references. We adopt the idea that the browser tool should resolve a target from the current snapshot and keep runtime element identifiers out of the long-term semantic plan.

### Chrome DevTools MCP
Chrome DevTools MCP is designed for live Chrome control and reliable automation, with waiting around actions. KAREEM_AGENT should treat Chrome as an execution surface and keep browser lifecycle state inside the browser tool, not in the semantic planner.

### Microsoft UFO
UFO uses a HostAgent/AppAgent split: an application-level coordinator decomposes work and a focused app agent performs application-specific actions. KAREEM_AGENT can scale toward the same shape later: a global planner chooses the surface, while browser/filesystem/Windows agents execute within their own capabilities.

### LangGraph
LangGraph persists graph state across interruptions and supports human approval/edit/reject flows with checkpoints. KAREEM_AGENT should move system-level sensitive operations to the same pattern: persist pending action, wait for approval, then resume from the same step.

### TARS
TARS emphasizes durable work records, recovery, proof-gated completion, tool policy, model tiers, and operator-visible run history. These are strong targets for the next KAREEM_AGENT stage: deterministic completion evidence, restart/retry/replay, and lightweight model tiers.

## V2 execution architecture

```text
User
  ↓
AnalyticalBrain
  ↓
GoalGraph (semantic intent)
  ↓
GoalState (runtime truth)
  ↓
DeterministicStepSelector  ← source of truth for next ready step
  ↓
ActionContract / Normalizer
  ↓
ToolExecutor
  ↓
Tool (Browser / Web / Files / System)
  ↓
Observation
  ↓
GoalState update
  ├── success → next ready step
  ├── transient failure → bounded retry
  ├── unsupported argument → compatibility normalization
  ├── repeated failure → recovery / replan
  └── sensitive system action → human approval checkpoint
```

## Hard rules

1. GoalState owns step order.
2. A successful required step cannot be scheduled again unless the user explicitly requests repetition.
3. The LLM cannot change the execution surface of a ready step.
4. Browser runtime IDs are resolved at execution time and are never semantic memory.
5. Unknown tools/actions fail fast.
6. Unsupported optional arguments are normalized once at the execution boundary; the same bad call is not retried blindly.
7. Completion is deterministic first, model verification second.
8. Sensitive Windows/system operations require approval and checkpoint/resume.
9. Every run should have an inspectable event trail.
10. Recovery must be bounded; never spend the full step budget on an identical failed action.

## Immediate fix delivered in this patch

- `brain/planner.py`: accepts `analysis` and `goal_state` plus future kwargs; picks the next GoalState step deterministically before using Qwen; normalizes aliases; prevents browser → web drift for a ready browser step.
- `tools/executor.py`: compatibility layer for argument drift such as `new_tab`, with bounded retry and explicit compatibility metadata.
- tests: deterministic planner preference and argument-drift regression coverage.

## Next development tranche

After this patch is installed and the Google/OpenAI scenario passes end-to-end, the next tranche should add:

- persistent run checkpoints;
- event/trace JSONL;
- browser element resolver + page fingerprint;
- recovery policies and bounded retry budgets;
- human approval interrupts for registry/services/firewall/driver/process-kill class operations;
- tiered local models (fast classifier, normal executor, heavy recovery planner);
- subagents for research/coding/browser tasks;
- a regression suite with long-horizon browser tasks and Windows tasks.

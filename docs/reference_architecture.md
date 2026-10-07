# KAREEM_AGENT Reference Architecture Research

This document records architecture lessons selected for KAREEM_AGENT from public open-source agent projects reviewed on 2026-10-07. These are design references, not copied implementations.

## PersonalJarvis
Repository: https://github.com/PersonalJarvis/PersonalJarvis

Useful ideas:
- Persistent agents with their own memory and reusable skills.
- A local knowledge/wiki layer that survives conversations.
- Visible computer/browser control with explicit tool/action boundaries.
- Agents improve through lessons from their own work.
- Long-running work should produce inspectable artifacts and tool-call history.

KAREEM_AGENT adoption:
- Keep experience/lesson memory separate from transient task history.
- Add reusable skill knowledge later rather than hard-coding workflows.
- Preserve evidence and trajectory history for learning.

## Agent S / Simular
Repository: https://github.com/simular-ai/Agent-S

Useful ideas:
- Natural-language goal -> grounded computer interaction without per-app scripts.
- The agent observes the actual GUI and acts from current evidence.
- Computer-use reasoning is separated from low-level interaction capabilities.
- Recent generations emphasize compositional planning and robust computer-use grounding.

KAREEM_AGENT adoption:
- Never map application names to fixed workflows.
- Inspect first when targets are unknown.
- Every UI action must be grounded in current observations.

## MonaW
Repository: https://github.com/kailiang0120/monaw

Useful ideas:
- Local-first Windows agent architecture.
- Explicit runtime/workspace/browser/memory state.
- Recovery and operational state are treated as first-class concerns.

KAREEM_AGENT adoption:
- Keep world state, run state, memory, and tool execution distinct.
- Make recovery a normal control path, not an exception-only hack.

## AIRI
Repository: https://github.com/varshney-ansh/airi

Useful ideas:
- Windows automation through inspectable UI Automation.
- Browser automation and filesystem operations exposed as model tools.
- Persistent semantic memory.

KAREEM_AGENT adoption:
- Prefer structured Windows inspection/control when available.
- Keep browser, computer, filesystem, and memory as capabilities the model can select.

## Thoth
Repository: https://github.com/tokwalabs/Thoth

Useful ideas:
- ReAct orchestration.
- Context trimming and focused context assembly.
- Structured long-term knowledge/semantic recall.
- Tool guardrails, approvals, recovery, and workflow state.
- Learning/refinement should improve durable knowledge instead of merely growing logs.

KAREEM_AGENT adoption:
- One reasoning/action cycle at a time.
- Keep prompts focused enough for local models.
- Verify completion with evidence.
- Store reusable lessons and refine them over time.

## Non-negotiable KAREEM_AGENT architecture

Tools provide capabilities; the model provides behavior.

The agent should follow:

USER GOAL
-> MODEL UNDERSTANDS GOAL
-> SELECTS TOOL/ACTION FROM LIVE CAPABILITIES
-> EXECUTES
-> OBSERVES RESULT
-> MODEL REASONS AGAIN
-> RECOVERS OR CONTINUES
-> VERIFIES EVIDENCE
-> STORES A REUSABLE LESSON

No application-specific workflow routing belongs in the agent core. Conditional code is allowed only for safety, validation, permissions, state consistency, retry limits, and other low-level execution concerns.

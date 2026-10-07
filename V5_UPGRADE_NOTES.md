# KAREEM_AGENT V5 — Perception + Goal Reasoning Upgrade

This release is a structural upgrade over V4. It is designed around the principle:

> observe -> understand -> compare with goal -> act -> observe again -> verify

## Implemented upgrades

1. Structured goal understanding before execution.
2. Semantic search query separated from output constraints.
3. Generic extraction of country, currency, price bounds, result count, and required fields.
4. Generic target-site resolution through public web search when a direct URL is not known.
5. Browser actions are followed by an automatic fresh inspection.
6. Accessibility snapshots are converted into a page world model.
7. Page type classification (search home, results, product, login, checkout, etc.).
8. Search-field discovery and semantic field targeting.
9. Result-link discovery from the current page rather than blind first-link clicking.
10. Region/currency perception from both URL and visible text.
11. Goal-vs-page relevance reasoning.
12. Country/currency mismatch detection.
13. Constraint-aware candidate extraction.
14. Deterministic price-bound verification.
15. Deterministic result-count verification.
16. Proof-gated completion: no "done" before the goal is proven.
17. Internal page-fingerprint tracking.
18. Repeated-action-on-same-state loop guard.
19. Reflexion-style failure analysis and lessons.
20. Append-only trajectory/experience memory.
21. Training-dataset export from successful/failed trajectories.
22. Run event traces in JSONL for replay/debugging.
23. Adaptive 80-step ceiling for longer workflows.
24. Planning context now includes goal, perception, state, reflections, memory, and knowledge.
25. Planner prefers deterministic cognitive hints before open-ended model actions.
26. Web search is used only as a resolver/research surface, not as a substitute for visible browser interaction.
27. Browser page inspection is treated as an observation, not as a mere navigation acknowledgement.
28. Final result formatting is built only from verified candidate evidence.
29. Existing V4 security/approval boundaries are preserved.
30. Existing browser, desktop, engineering, learning, knowledge, memory, repair, and security tools remain registered.

## Learning strategy

The agent does not need a model-weight update to learn immediately. Successful and failed trajectories are stored in `data/experiences/trajectories.jsonl` with goal, state, actions, outcomes, and reflections. This is used as episodic learning and can later be exported as `training_dataset.jsonl` for LoRA/SFT or preference training.

## Research patterns used

The design borrows the following ideas without copying any one project wholesale:

- OpenHands: explicit reasoning/action/tool/event separation and security validation.
- Playwright MCP: accessibility snapshots, stable element references, and re-snapshot after page changes.
- Microsoft UFO²: hierarchical orchestration, persistent state machines, application-aware execution, and shared blackboard-style state.
- Agent S: separate perception/grounding from high-level planning, reflection, and trajectory scaling.
- WebArena / OSWorld / OSWorld 2.0: long-horizon tasks, execution-based evaluation, hidden state, and verification pressure.
- Reflexion: failure -> reflection -> episodic lesson -> improved future attempt.
- Voyager: an ever-growing skill library and continual experience-based improvement.
- SWE-agent: tight agent-computer interfaces with small observable actions and feedback loops.

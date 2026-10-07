# KAREEM_AGENT V6 — World-State + Tool Handoff Upgrade

## What changed

1. Added a generic discovery-to-execution handoff router.
2. `web.search` success now feeds `browser.open_url` automatically.
3. Successful discovery cannot immediately repeat itself.
4. Browser becomes the interaction executor for website tasks.
5. Goal parsing is stricter about separating semantic query from constraints.
6. Country/currency/price/count are kept outside the search query.
7. Search query cleanup removes navigation prefixes and output clauses.
8. Page perception gets richer goal context.
9. Page perception JSON parsing tolerates fenced/model-wrapped JSON.
10. Saudi/UAE region URLs can provide country/currency evidence.
11. Search result detection recognizes both `/search` and `?q=` contexts.
12. State reasoner uses visible result links as secondary evidence.
13. State reasoner deduplicates candidate URLs.
14. Query matching uses term overlap rather than all-or-nothing exact naming.
15. Completion is still proof-gated on requested candidate count.
16. Completion requires requested result fields and constraints.
17. Wrong-context pages get a controlled perception pass instead of an inspect loop.
18. Planner gives V6 cognition authority over stale legacy DAG planning.
19. Legacy GoalState compatibility remains available for explicit old tests/callers.
20. BrowserGoalController remains only a fallback for simple tasks.
21. Reflection/loop guard remain active.
22. Experience capture keeps longer trajectories for later training.
23. No Noon-specific execution branch was added.
24. No region-specific site scraper was added.
25. Unit tests cover Web→Browser handoff and successful discovery anti-loop behavior.
26. Query-cleaning tests cover Saudi/currency/price stripping.
27. Completion proof tests require five eligible results.
28. Compile checks cover brain/core/tools/tests.

## Research basis

The architecture is informed by open-source agent patterns including OpenHands' reasoning-action loop and tool orchestration, Microsoft UFO²'s HostAgent/AppAgent separation, persistent state machine, hybrid execution, knowledge substrate, and iterative UI re-annotation, plus ReAct-style iterative observation/action patterns.

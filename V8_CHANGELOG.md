# KAREEM_AGENT V8 — Cognition Stability

- Named common sites now resolve to a canonical `start_url`, so Google/Noon/Amazon/etc. do not waste steps searching for their own homepages.
- Search-query extraction removes trailing action phrases such as `وافـتح أول نتيجة`, preventing `OpenAI وافتح` from becoming the query.
- Unknown-site web discovery allows at most two consecutive failed searches and then fails closed instead of looping.
- Planner can emit a terminal `__TASK_FAILED__` result and runner returns immediately.
- Runtime banner and planner prompt updated to V8.

This release keeps the V7 browser session safety boundary.

# KAREEM_AGENT V9 — World-State / Completion Gate Fix

This release replaces the fragile V8.x loop behavior with deterministic world-state rules around browser action goals.

## Core fixes
- A page is only `search_home` when an interactive field itself is a search field. A generic text box plus the words "Open Search" no longer turns arbitrary pages into search pages.
- `browser.click(first_result=True)` creates a completion proof when the current page reaches the clicked destination origin.
- Completion proof is authoritative for first-result action goals and cannot be vetoed by a noisy page classifier.
- Runner checks deterministic completion before asking the planner for another action.
- Repeating the exact same action on the same page fingerprint is fail-closed after two repeats instead of spinning through dozens of steps.
- Completion proof is carried in cognitive state for traceability.

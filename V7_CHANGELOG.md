# KAREEM_AGENT V7 — Browser Session Safety

V7 is a safety-focused upgrade on top of V6. The key bug fixed here is browser-session drift: when Chrome DevTools MCP fails while the selected tab is the KAREEM_AGENT Flask UI, the agent must never fall back to that local chat textbox and treat it as a website search field.

## Main changes
- Browser target binding to an exact runtime page ID and expected origin.
- External targets opened from KAREEM_AGENT UI use a real Chrome page and are bound before actions continue.
- Failed navigation keeps the intended target binding and fails closed instead of silently selecting another tab.
- Every browser mutation is guarded against page/origin drift.
- KAREEM_AGENT own Flask UI is explicitly classified as `agent_control_ui`.
- StateReasoner marks that context as `wrong_context` for external site tasks.
- A failed `browser.open_url` does not count as a successful handoff.
- Search fields already containing the target query are submitted instead of refilled.
- Installer/update scripts now copy `brain`, `core`, `tools`, and `tests` together.

## Expected behavior
The agent may use the current Chrome session, but it must never control its own KAREEM_AGENT chat page as a website target. Chrome itself is not intentionally closed by V7.

# KAREEM_AGENT V8.2 — Browser Rebind & Completion Gate

## Root-cause fixes

1. A successful browser click that navigates to a new origin now rebases the bound browser session to the actual destination.
2. The next automatic perception pass is no longer rejected as false "browser target drift".
3. A successful first-result click is completion-proofed against the actual destination origin; the agent can stop immediately once it has reached the requested result page.
4. A regression test ensures the drift guard still fails closed before an action when a page unexpectedly changes outside a successful navigation action.

This release does not weaken the anti-self-control safety rule: actions cannot silently fall back to the KAREEM_AGENT local UI.

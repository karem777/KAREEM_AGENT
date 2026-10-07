# V8 Handoff

The important V7 browser binding safety is preserved. V8 additionally fixes the test failure where:
1. Goal query became `OpenAI وافتح`.
2. Google was discovered through web search instead of opening the known homepage directly.
3. Failed web searches could repeat indefinitely.
4. A terminal planning failure had no immediate stop path.

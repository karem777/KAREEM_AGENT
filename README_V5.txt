KAREEM_AGENT V5
================

This build replaces the old "navigation script" mindset with a cognition loop.

USER GOAL -> GOAL MODEL -> PAGE PERCEPTION -> STATE REASONING -> ACTION -> OBSERVE -> VERIFY

Main new modules:
- brain/goal_understanding.py
- brain/page_perception.py
- brain/state_reasoner.py
- brain/reflection.py
- core/cognition.py
- core/trace.py
- learning/experience.py

Run:
1. Back up the current KAREEM_AGENT folder.
2. Replace the project files with this package (or run INSTALL_V5.bat).
3. Start the agent as usual with START_AGENT.bat or python app.py.

Useful local artifacts:
- data/experiences/trajectories.jsonl
- data/experiences/training_dataset.jsonl
- data/traces/run_*.jsonl

The agent still uses the user's existing Chrome session.
Sensitive Windows operations keep the existing approval boundaries.

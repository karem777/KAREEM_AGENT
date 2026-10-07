import time
from brain.local_brain import LocalBrain

brain = LocalBrain()

prompt = '''Return JSON only:
{"type":"tool_call","tool":"filesystem","action":"create_directory","arguments":{"path":"speed_test"}}'''

start = time.time()
result = brain.ask(prompt)
elapsed = time.time() - start

print("\n===== SPEED TEST =====")
print(f"Time: {elapsed:.2f} seconds")
print(result)

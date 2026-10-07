import time
from brain.local_brain import LocalBrain

brain = LocalBrain()

start = time.time()

result = brain.ask(
    'Return only this JSON: {"ok": true}'
)

elapsed = time.time() - start

print()
print("===== LOCAL BRAIN SPEED TEST =====")
print(f"TIME: {elapsed:.2f} seconds")
print("RESPONSE:")
print(result)

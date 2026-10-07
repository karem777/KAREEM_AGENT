import time
from core.runner import AgentRunner

runner = AgentRunner("workspace")

start = time.time()
result = runner.run("اعمل فولدر اسمه speed_test_3")
elapsed = time.time() - start

print()
print("===== AGENT SPEED TEST =====")
print(f"TOTAL TIME: {elapsed:.2f} seconds")
print("RESULT:")
print(result)

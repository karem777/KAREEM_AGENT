import time
from ollama import chat

start = time.time()

response = chat(
    model="qwen3:8b",
    messages=[
        {
            "role": "user",
            "content": "Return only this JSON: {\"ok\": true}"
        }
    ],
    think=False
)

elapsed = time.time() - start

print()
print("===== RAW OLLAMA SPEED TEST =====")
print(f"TIME: {elapsed:.2f} seconds")
print("RESPONSE:")
print(response.message.content)

from brain.memory import Memory

memory = Memory()

print("=== MEMORY TEST ===")

print("\nSET:")
print(memory.set("user_name", "كريم"))

print("\nGET:")
print(memory.get("user_name"))

print("\nALL:")
print(memory.all())

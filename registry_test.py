from tools.registry import ToolRegistry

registry = ToolRegistry("workspace")

print("=== REGISTRY TEST ===")
print()

print("TOOLS:")
print(registry.names())

print()
print("COUNT:")
print(registry.count())

print()
print("DESCRIPTIONS:")
print(registry.describe())

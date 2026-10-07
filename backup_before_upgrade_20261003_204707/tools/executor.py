class ToolExecutor:
    def __init__(self, registry):
        self.registry = registry

    def execute(self, tool_name, action, **kwargs):
        tool = self.registry.get(tool_name)

        if tool is None:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}"
            }

        method = getattr(tool, action, None)

        if method is None or action.startswith("_"):
            return {
                "success": False,
                "error": f"Action not found: {action}"
            }

        try:
            result = method(**kwargs)

            return {
                "success": True,
                "result": result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def describe_tools(self):
        return self.registry.describe()

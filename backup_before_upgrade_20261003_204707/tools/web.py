from ddgs import DDGS


class WebTool:
    name = "web"
    description = "Search the internet and return web results."

    def search(self, query, max_results=5):
        try:
            results = DDGS().text(
                query,
                max_results=max_results
            )

            return {
                "success": True,
                "results": results
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def describe(self):
        return {
            "name": self.name,
            "description": self.description,
            "actions": {
                "search": {
                    "description": "Search the internet.",
                    "parameters": {
                        "query": {
                            "type": "string",
                            "required": True
                        },
                        "max_results": {
                            "type": "integer",
                            "required": False,
                            "default": 5
                        }
                    }
                }
            }
        }
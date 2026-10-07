from tools.executor import ToolExecutor


class FakeBrowser:
    name = "browser"

    def open_url(self, url):
        return {"opened": url}


class Registry:
    def __init__(self):
        self.tool = FakeBrowser()

    def get(self, name):
        return self.tool if name == "browser" else None

    def describe(self):
        return {"browser": {"actions": {"open_url": {}}}}


def test_new_tab_keyword_drift_does_not_loop():
    executor = ToolExecutor(Registry())
    result = executor.execute("browser", "open_url", url="https://openai.com", new_tab=True)
    assert result["success"] is True
    assert result["compatibility"]["dropped_argument"] == "new_tab"

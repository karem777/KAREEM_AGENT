import re


class ToolRouter:
    """Keep the tool catalog compact without hiding research, memory, or Windows capabilities."""

    GROUPS = {
        "browser": {"browser", "web", "research"},
        "computer": {"computer", "windows", "desktop"},
        "files": {"filesystem", "developer", "knowledge", "learning"},
        "memory": {"memory", "experience", "knowledge", "learning"},
        "research": {"browser", "web", "research", "knowledge", "learning"},
        "system": {"windows", "computer"},
    }

    KEYWORDS = {
        "browser": r"browser|chrome|صفح|موقع|رابط|افتح|ادخل|جوجل|google|bing|بحث|search|url|ويب|website",
        "computer": r"كمبيوتر|شاشة|نافذة|اضغط|انقر|اكتب|كيبورد|ماوس|desktop|computer|click|type|press|vscode|vs code|visual studio code",
        "files": r"ملف|ملفات|مجلد|folder|file|pdf|txt|doc|code|كود|برمج|مشروع|repository|repo|github|vscode|vs code|visual studio code",
        "memory": r"افتكر|تذكر|ذاكرة|memory|remember|نسيت|محفوظ|experience|خبرة|اتعلم|تعلم|learn",
        "research": r"ابحث|بحث|دور|معلومات|قارن|research|search|find|github|مشاريع|project|latest|آخر|مش عارف|لا اعرف|unknown|documentation|docs",
        "system": r"ويندوز|windows|نظام|process|برنامج|خدمة|شبكة|network|storage|cpu|ram|system|تثبيت|install|powershell|power shell|terminal|command line|cmd",
    }

    def select(self, request: str, available: dict | None = None) -> set[str]:
        names = set((available or {}).keys())
        names.discard("_load_errors")
        if not names:
            return set()

        text = " ".join(str(request).lower().split())
        groups = {group for group, pattern in self.KEYWORDS.items() if re.search(pattern, text, re.I)}

        if not groups:
            preferred = {"computer", "browser", "filesystem", "windows", "web", "memory", "learning", "knowledge", "experience", "research"}
        else:
            preferred = set()
            for group in groups:
                preferred.update(self.GROUPS.get(group, set()))
            # Keep verified web research and reusable knowledge available to any task.
            preferred.update({"web", "learning", "knowledge", "memory", "experience"})
            if "computer" in names:
                preferred.add("computer")
            # Chrome/browser interaction is available when unfamiliar work needs live UI research.
            if "browser" in names:
                preferred.add("browser")

        selected = names & preferred
        return selected or names

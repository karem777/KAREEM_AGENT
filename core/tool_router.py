import re


class ToolRouter:
    """Small deterministic router that narrows the live tool catalog before planning."""

    GROUPS = {
        "browser": {"browser", "web", "research"},
        "computer": {"computer", "windows", "desktop"},
        "files": {"filesystem", "developer", "knowledge", "learning"},
        "memory": {"memory", "experience"},
        "research": {"web", "research", "knowledge", "learning"},
        "system": {"windows", "computer"},
    }

    KEYWORDS = {
        "browser": r"browser|صفح|موقع|رابط|افتح|ادخل|جوجل|google|bing|بحث|search|url|ويب|website",
        "computer": r"كمبيوتر|شاشة|نافذة|اضغط|انقر|اكتب|كيبورد|ماوس|desktop|computer|click|type|press",
        "files": r"ملف|ملفات|مجلد|folder|file|pdf|txt|doc|code|كود|برمج|مشروع|repository|repo|github",
        "memory": r"افتكر|تذكر|ذاكرة|memory|remember|نسيت|محفوظ|experience|خبرة",
        "research": r"ابحث|بحث|دور|معلومات|قارن|research|search|find|github|مشاريع|project|latest|آخر",
        "system": r"ويندوز|windows|نظام|process|برنامج|خدمة|شبكة|network|storage|cpu|ram|system|تثبيت|install",
    }

    def select(self, request: str, available: dict | None = None) -> set[str]:
        names = set((available or {}).keys())
        names.discard("_load_errors")
        if not names:
            return set()

        text = " ".join(str(request).lower().split())
        groups = {group for group, pattern in self.KEYWORDS.items() if re.search(pattern, text, re.I)}

        if not groups:
            # Ambiguous tasks keep a useful but compact general catalog.
            preferred = {"computer", "browser", "filesystem", "windows", "web", "memory"}
        else:
            preferred = set()
            for group in groups:
                preferred.update(self.GROUPS.get(group, set()))
            # Every action task should retain a way to observe/control the machine.
            if "computer" in names:
                preferred.add("computer")

        selected = names & preferred
        # Keep memory/experience available when the task is ambiguous or personal.
        if "memory" in names and (not groups or "memory" in groups):
            selected.add("memory")
        if "experience" in names and (not groups or "memory" in groups):
            selected.add("experience")

        # Never return an empty catalog; the full catalog is safer than guessing wrong.
        return selected or names

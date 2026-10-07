import json
import re
from brain.local_brain import LocalBrain


class AnalyticalBrain:
    """Goal graph builder with deterministic browser-intent routing for common sites."""

    def __init__(self):
        self.brain = LocalBrain()
        self.site_aliases = {
            "google": "https://www.google.com",
            "جوجل": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "يوتيوب": "https://www.youtube.com",
            "gmail": "https://mail.google.com",
            "جيميل": "https://mail.google.com",
            "github": "https://github.com",
            "جيت هب": "https://github.com",
            "chatgpt": "https://chatgpt.com",
            "شات جي بي تي": "https://chatgpt.com",
            "whatsapp": "https://web.whatsapp.com",
            "واتساب": "https://web.whatsapp.com",
            "noon": "https://www.noon.com/",
            "نون": "https://www.noon.com/",
            "نون السعودية": "https://www.noon.com/",
            "amazon": "https://www.amazon.sa/",
            "امازون": "https://www.amazon.sa/",
            "أمازون": "https://www.amazon.sa/",
        }

    @staticmethod
    def _clean_json(raw):
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
        return text

    def _parse(self, raw):
        text = self._clean_json(raw)
        for _ in range(4):
            try:
                value = json.loads(text)
            except Exception:
                match = re.search(r"\{[\s\S]*\}", text)
                if not match:
                    return None
                try:
                    value = json.loads(match.group(0))
                except Exception:
                    return None
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                text = value
                continue
            return None
        return None

    def _site_hint(self, user_message):
        text = str(user_message).strip().lower()
        # Longest aliases first prevents "نون" matching inside a longer alias.
        found = []
        for alias, url in sorted(self.site_aliases.items(), key=lambda x: len(x[0]), reverse=True):
            if alias in text:
                found.append((alias, url))
        return dict(found)

    def _extract_search_query(self, message):
        text = str(message or "").strip()
        patterns = [
            r"(?:ابحث|دور|دورلي|ابحثلي|ابحث عن|ابحث في|ابحث على)\s+(?:عن\s+)?(.+)$",
            r"(?:search|find)\s+(?:for\s+)?(.+)$",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                value = m.group(1).strip(" .،،")
                if value:
                    # Keep the search phrase but strip a trailing site reference.
                    value = re.sub(r"\s+(?:في|على|داخل)\s+(?:نون|noon|جوجل|google)\s*$", "", value, flags=re.IGNORECASE)
                    return value
        return ""

    def _price_constraint(self, message):
        text = str(message or "")
        m = re.search(r"(?:أقل من|اقل من|تحت|بسعر أقل من|under|less than)\s*(\d+(?:\.\d+)?)\s*(?:ريال|ر\.س|sar|sr)?", text, flags=re.IGNORECASE)
        if not m:
            return None
        try:
            value = float(m.group(1))
            return {"max_price": int(value) if value.is_integer() else value, "currency": "SAR"}
        except Exception:
            return None

    def _build_browser_site_workflow(self, user_message):
        """Handle explicit 'enter site + do something' intent without falling into web.search."""
        text = str(user_message or "").strip()
        lower = text.lower()
        hints = self._site_hint(text)
        if not hints:
            return None

        # This route is intentionally limited to explicit browser interaction language.
        browser_words = (
            "ادخل", "افتح", "روح", "خش", "ادخل على", "افتحلي",
            "go to", "open", "visit"
        )
        if not any(word in lower for word in browser_words):
            return None

        alias, url = next(iter(hints.items()))
        steps = [
            {
                "id": "s1",
                "kind": "action",
                "description": f"Open {alias} in the current Chrome session.",
                "tool": "browser",
                "action": "open_url",
                "arguments": {"url": url},
                "depends_on": [],
                "required": True,
                "success_signal": {"url_contains": url.split("//", 1)[-1].split("/", 1)[0]},
            },
            {
                "id": "s2",
                "kind": "action",
                "description": "Inspect the opened site before interacting with it.",
                "tool": "browser",
                "action": "inspect",
                "arguments": {},
                "depends_on": ["s1"],
                "required": True,
                "success_signal": {"snapshot": True},
            },
        ]

        query = self._extract_search_query(text)
        constraints = {}
        price = self._price_constraint(text)
        if price:
            constraints["price"] = price

        # For a search request, create a semantic fill step. BrowserTool V3.2 can resolve
        # a search field from the latest accessibility snapshot, so we do not invent a UID.
        if query:
            steps.append(
                {
                    "id": "s3",
                    "kind": "action",
                    "description": f"Fill the site's search field with: {query}",
                    "tool": "browser",
                    "action": "fill",
                    "arguments": {"target": "search", "value": query},
                    "depends_on": ["s2"],
                    "required": True,
                    "success_signal": {"field_filled": True},
                }
            )
            steps.append(
                {
                    "id": "s4",
                    "kind": "action",
                    "description": "Submit the site search form.",
                    "tool": "browser",
                    "action": "press_key",
                    "arguments": {"key": "ENTER"},
                    "depends_on": ["s3"],
                    "required": True,
                    "success_signal": {"submitted": True},
                }
            )
            steps.append(
                {
                    "id": "s5",
                    "kind": "action",
                    "description": "Inspect the search results and verify they match the requested search.",
                    "tool": "browser",
                    "action": "inspect",
                    "arguments": {},
                    "depends_on": ["s4"],
                    "required": True,
                    "success_signal": {"snapshot": True},
                }
            )

        return {
            "schema_version": "1.2",
            "mode": "execute",
            "language": "ar",
            "goal": text,
            "answer": "",
            "entities": [
                {"type": "site", "name": alias, "value": url},
                *([{"type": "search", "value": query}] if query else []),
            ],
            "constraints": constraints,
            "steps": steps,
            "fallbacks": [],
            "completion": {
                "required_steps": [step["id"] for step in steps],
                "description": "Every required browser interaction step must complete successfully.",
            },
        }

    def _normalize_steps(self, plan):
        steps = []
        raw_steps = plan.get("steps", [])
        if not isinstance(raw_steps, list):
            raw_steps = []
        used = set()
        for index, raw in enumerate(raw_steps, 1):
            if not isinstance(raw, dict):
                continue
            step_id = str(raw.get("id", f"s{index}")).strip() or f"s{index}"
            if step_id in used:
                step_id = f"s{index}_{len(used)+1}"
            while step_id in used:
                step_id = f"s{index}_{len(used)+1}"
            used.add(step_id)
            arguments = raw.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            if str(raw.get("tool", "")).strip() == "browser" and str(raw.get("action", "")).strip() in {"inspect", "click", "fill"}:
                if arguments.get("page_id") in (None, "", "0", "-1"):
                    arguments.pop("page_id", None)
            depends_on = raw.get("depends_on", [])
            if not isinstance(depends_on, list):
                depends_on = []
            depends_on = [str(x).strip() for x in depends_on if str(x).strip()]
            steps.append({
                "id": step_id,
                "kind": str(raw.get("kind", "action")).strip(),
                "description": str(raw.get("description", "")).strip(),
                "tool": str(raw.get("tool", "")).strip(),
                "action": str(raw.get("action", "")).strip(),
                "arguments": arguments,
                "depends_on": depends_on,
                "required": bool(raw.get("required", True)),
                "success_signal": raw.get("success_signal", {}) if isinstance(raw.get("success_signal", {}), dict) else {},
            })
        return steps

    def _repair(self, plan):
        if not plan:
            return None
        steps = self._normalize_steps(plan)
        known = {step["id"] for step in steps}
        position = {step["id"]: idx for idx, step in enumerate(steps)}
        for step in steps:
            deps = []
            for dep in step["depends_on"]:
                if dep in known and dep != step["id"] and position[dep] < position[step["id"]]:
                    deps.append(dep)
            step["depends_on"] = deps
        mode = str(plan.get("mode", "execute")).strip().lower()
        if mode not in {"chat", "execute", "research", "clarify"}:
            mode = "execute"
        required_steps = [s["id"] for s in steps if s["required"]]
        return {
            "schema_version": "1.2",
            "mode": mode,
            "language": str(plan.get("language", "ar")),
            "goal": str(plan.get("goal", "")).strip(),
            "answer": str(plan.get("answer", "")).strip(),
            "entities": plan.get("entities", []) if isinstance(plan.get("entities", []), list) else [],
            "constraints": plan.get("constraints", {}) if isinstance(plan.get("constraints", {}), dict) else {},
            "steps": steps,
            "fallbacks": plan.get("fallbacks", []) if isinstance(plan.get("fallbacks", []), list) else [],
            "completion": {"required_steps": required_steps, "description": "Every required step must complete successfully."},
        }

    def _repair_empty_tool_args(self, plan, user_message):
        """Repair the specific class of bad plans that call web.search/open_url without arguments."""
        if not isinstance(plan, dict):
            return plan
        for step in plan.get("steps", []) if isinstance(plan.get("steps", []), list) else []:
            if not isinstance(step, dict):
                continue
            tool = str(step.get("tool", "")).strip().lower()
            action = str(step.get("action", "")).strip().lower()
            args = step.get("arguments")
            if not isinstance(args, dict):
                args = {}
                step["arguments"] = args
            if tool == "web" and action == "search" and not args.get("query"):
                # Never leave a required web.search call malformed.
                args["query"] = str(user_message or "").strip()
                args.setdefault("max_results", 5)
        return plan

    def analyze(self, user_message, available_tools=None, previous_goal=None):
        deterministic = self._build_browser_site_workflow(user_message)
        if deterministic is not None:
            return self._repair(deterministic)

        prompt = (
            "You are the ANALYTICAL BRAIN of KAREEM_AGENT.\n"
            "Interpret natural language and build an ordered goal graph.\n\n"
            "USER MESSAGE:\n" + str(user_message) + "\n\n"
            "AVAILABLE TOOLS:\n" + json.dumps(available_tools or {}, ensure_ascii=False, separators=(",", ":")) + "\n\n"
            "COMMON SITE HINTS:\n" + json.dumps(self._site_hint(user_message), ensure_ascii=False, separators=(",", ":")) + "\n\n"
            "PREVIOUS GOAL:\n" + json.dumps(previous_goal or {}, ensure_ascii=False, separators=(",", ":")) + "\n\n"
            "Rules:\n"
            "- If the user explicitly asks to open/enter a website and interact with it, use browser, not web.\n"
            "- A multi-action request must become multiple ordered steps.\n"
            "- Never emit an empty web.search query.\n"
            "- Never invent browser page IDs or UIDs.\n"
            "- For browser interaction, inspect the page before using element-specific actions.\n"
            "Return JSON only."
        )
        raw = self.brain.ask(prompt)
        plan = self._parse(raw)
        if plan is None:
            repair_prompt = "Repair this into valid KAREEM_AGENT analytical JSON. Do not invent data. Return JSON only.\nUSER:\n" + str(user_message) + "\nRAW:\n" + str(raw)
            plan = self._parse(self.brain.ask(repair_prompt))
        plan = self._repair_empty_tool_args(plan or {}, user_message)
        return self._repair(plan)

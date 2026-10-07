from __future__ import annotations

import json
import re
from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.local_brain import LocalBrain


class GoalUnderstanding:
    """Turns natural language into a reusable, site-agnostic goal model.

    Deterministic extraction is applied first for hard constraints (price,
    currency, count, country). The local model is then used only to fill in
    semantic fields that are hard to infer with regular expressions.
    """

    CURRENCY_PATTERNS = {
        "SAR": r"(?:ر\.س|ر\.س\.?|ريال(?:\s+سعودي|\s+سعودية)?|sar|saudi\s+riy(?:al|als)?)",
        "AED": r"(?:د\.إ|درهم(?:\s+إماراتي|\s+اماراتي)?|aed|uae\s+dirham)\b",
        "EGP": r"(?:ج\.م|جنيه(?:\s+مصري)?|egp|egyptian\s+pounds?)\b",
        "USD": r"(?:\$|usd|dollars?|دولار)\b",
        "EUR": r"(?:€|eur|euros?|يورو)\b",
    }

    COUNTRY_HINTS = {
        "Saudi Arabia": ["السعودية", "السعوديه", "saudi", "ksa", "المملكة العربية السعودية"],
        "United Arab Emirates": ["الإمارات", "الامارات", "uae", "emirates", "دبي"],
        "Egypt": ["مصر", "المصري", "egypt", "cairo"],
        "United States": ["امريكا", "أمريكا", "usa", "united states", "us"],
    }

    SITE_HINTS = {
        "noon": ["نون", "noon"],
        "amazon": ["امازون", "أمازون", "amazon"],
        "aliexpress": ["aliexpress", "علي اكسبريس", "علي إكسبريس"],
        "booking": ["booking", "بوكينج", "booking.com"],
        "github": ["github", "جيت هب"],
        "google": ["google", "جوجل"],
        "youtube": ["youtube", "يوتيوب"],
        "whatsapp": ["whatsapp", "واتساب"],
    }

    KNOWN_SITE_URLS = {
        "noon": "https://www.noon.com/",
        "amazon": "https://www.amazon.sa/",
        "aliexpress": "https://www.aliexpress.com/",
        "booking": "https://www.booking.com/",
        "github": "https://github.com/",
        "google": "https://www.google.com/",
        "youtube": "https://www.youtube.com/",
        "whatsapp": "https://web.whatsapp.com/",
    }

    def __init__(self, brain: LocalBrain | None = None):
        if brain is None:
            from brain.local_brain import LocalBrain
            brain = LocalBrain()
        self.brain = brain

    @staticmethod
    def _json(raw: str) -> dict[str, Any] | None:
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else None
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                return None
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None

    def _deterministic(self, text: str) -> dict[str, Any]:
        low = text.casefold()
        out: dict[str, Any] = {
            "goal_type": "general_task",
            "site": None,
            "start_url": None,
            "country": None,
            "currency": None,
            "query": None,
            "constraints": {},
            "result_count": None,
            "required_fields": [],
            "requires_search": bool(re.search(r"\b(?:ابحث|دور|search|find)\b", low)),
            "requires_first_result": bool(re.search(r"(?:أول|اول|first)\s+(?:نتيجة|result)", low)),
            "requires_data_collection": False,
            "raw": text,
        }

        url = re.search(r"https?://[^\s،,؛;]+", text, flags=re.I)
        if url:
            out["start_url"] = url.group(0).rstrip(".,،)")

        for site, hints in self.SITE_HINTS.items():
            if any(h.casefold() in low for h in hints):
                out["site"] = site
                break

        if not out["start_url"] and out.get("site") in self.KNOWN_SITE_URLS:
            out["start_url"] = self.KNOWN_SITE_URLS[out["site"]]

        for country, hints in self.COUNTRY_HINTS.items():
            if any(h.casefold() in low for h in hints):
                out["country"] = country
                break

        for cur, pat in self.CURRENCY_PATTERNS.items():
            if re.search(pat, text, flags=re.I):
                out["currency"] = cur
                break

        max_price = re.search(
            r"(?:أقل من|اقل من|حد أقصى|حتى|maximum|max|under|below|less than)\s*([\d,.]+)",
            text,
            flags=re.I,
        )
        if max_price:
            try:
                out["constraints"]["max_price"] = float(max_price.group(1).replace(",", ""))
            except ValueError:
                pass

        min_price = re.search(
            r"(?:أعلى من|اكبر من|من\s+السعر|minimum|min|above|over|more than)\s*([\d,.]+)",
            text,
            flags=re.I,
        )
        if min_price:
            try:
                out["constraints"]["min_price"] = float(min_price.group(1).replace(",", ""))
            except ValueError:
                pass

        count = re.search(r"(?:أول|اول|first)\s*([0-9٠-٩]+)\s*(?:نتائج|نتيجة|results|result)", text, flags=re.I)
        if count:
            raw = count.group(1).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
            out["result_count"] = int(raw)
        elif out["requires_first_result"]:
            out["result_count"] = 1

        if re.search(r"(?:الاسم|name)", text, flags=re.I):
            out["required_fields"].append("name")
        if re.search(r"(?:السعر|price)", text, flags=re.I):
            out["required_fields"].append("price")
        if re.search(r"(?:الرابط|لينك|link|url)", text, flags=re.I):
            out["required_fields"].append("url")
        if out["result_count"] or len(out["required_fields"]) >= 2:
            out["requires_data_collection"] = True

        if any(x in low for x in ["اعرض", "هات", "أظهر", "قولي", "show", "list"]):
            out["requires_data_collection"] = True

        if out["requires_search"]:
            out["goal_type"] = "web_search"
        if out["requires_data_collection"]:
            out["goal_type"] = "web_research"
        if any(x in low for x in ["اكتب كود", "برمج", "debug", "صلح الكود", "write code"]):
            out["goal_type"] = "software_engineering"
        if any(x in low for x in ["اتعلم", "تعلم", "learn", "study"]):
            out["goal_type"] = "learning"

        return out

    def _extract_query(self, text: str, seed: dict[str, Any]) -> str | None:
        """Extract only the semantic search query, leaving constraints separate."""
        original = str(text or "").strip()
        q = original

        # Prefer the natural-language search clause when present.
        m = re.search(
            r"(?:ابحث(?:\s+لي)?|دور(?:\s+لي)?|search|find)\s+(?:عن|على|في|for)?\s*(?P<query>.+)",
            q,
            flags=re.I,
        )
        if m:
            q = m.group("query")

        # Remove trailing output/verification/action clauses. This keeps
        # "OpenAI" from becoming "OpenAI وافتح" in requests such as:
        # "افتح جوجل وابحث عن OpenAI وافتح أول نتيجة".
        q = re.split(
            r"\s+(?:و?افتح|و?ادخل|و?اعرض|و?أظهر|و?طلع|و?هاتلي|و?هات|show|list|return|give me|with|بالاسم|والسعر|والرابط)\b",
            q,
            maxsplit=1,
            flags=re.I,
        )[0]

        q = re.sub(
            r"\s+(?:أول|اول|first)(?:\s+[0-9٠-٩]+)?\s*(?:نتيجة|result)\s*$",
            "",
            q,
            flags=re.I,
        )

        # Remove site/navigation prefixes that may remain before the query.
        q = re.sub(
            r"^(?:افتح|ادخل(?:\s+على)?|روح(?:\s+على)?|خش(?:\s+على)?|open|visit)\s+(?:موقع\s+)?(?:نون|noon|أمازون|امازون|amazon|google|جوجل|github|جيت هب|aliexpress|علي\s*إكسبريس|booking|بوكينج)\b",
            " ",
            q,
            flags=re.I,
        )
        q = re.sub(r"^(?:السعودية|السعوديه|saudi arabia|ksa|المملكة العربية السعودية)\s*(?:و|and)?\s*", "", q, flags=re.I)

        # Remove explicit price/currency/count constraints from the semantic query.
        q = re.sub(r"(?:أقل من|اقل من|حتى|حد أقصى|under|below|less than)\s*[\d,.]+", "", q, flags=re.I)
        q = re.sub(r"(?:أعلى من|اكبر من|على الأقل|at least|minimum|min|above|over|more than)\s*[\d,.]+", "", q, flags=re.I)
        q = re.sub(r"(?:ب(?:سعر|سعر)?|بسعر|السعر|price)\s*$", "", q, flags=re.I)
        q = re.sub(r"\b(?:بسعر|بالسعر|السعر)\b", " ", q, flags=re.I)
        q = re.sub(r"(?:ريال(?:\s+سعودي)?|ر\.س|sar|درهم(?:\s+إماراتي)?|aed|د\.إ|جنيه(?:\s+مصري)?|egp|دولار|usd)\b", "", q, flags=re.I)
        q = re.sub(r"(?:أول|اول|first)\s*[0-9٠-٩]*\s*(?:نتائج|نتيجة|results|result)", "", q, flags=re.I)
        q = re.sub(r"\s+", " ", q).strip(" ،,؛;.-")

        # If regex extraction is empty, fall back to the deterministic seed.
        return q or seed.get("query")

    def understand(self, user_message: str) -> dict[str, Any]:
        seed = self._deterministic(str(user_message or ""))
        prompt = f"""
You are the Goal Understanding module of a local autonomous computer agent.
Convert the user's request into a compact structured goal. Do not execute anything.
Do not invent URLs or site facts. Preserve hard constraints exactly.

USER REQUEST:
{user_message}

DETERMINISTIC EXTRACTION (may contain partial fields; treat it as evidence):
{json.dumps(seed, ensure_ascii=False)}

Return JSON only with exactly these keys:
{{
  "goal_type": "general_task|web_search|web_research|software_engineering|windows_diagnostic|learning|chat",
  "site": null,
  "start_url": null,
  "country": null,
  "currency": null,
  "query": null,
  "constraints": {{}},
  "result_count": null,
  "required_fields": [],
  "requires_search": false,
  "requires_first_result": false,
  "requires_data_collection": false,
  "verification": [],
  "ambiguities": []
}}
"""

        try:
            model_obj = self._json(self.brain.ask(prompt)) or {}
        except Exception:
            model_obj = {}

        result = {**seed, **{k: v for k, v in model_obj.items() if v not in (None, "", [], {})}}
        result.setdefault("constraints", {})
        result["constraints"] = {**seed.get("constraints", {}), **(model_obj.get("constraints") or {})}
        result.setdefault("required_fields", [])
        result["required_fields"] = list(dict.fromkeys([*seed.get("required_fields", []), *(model_obj.get("required_fields") or [])]))
        deterministic_query = self._extract_query(str(user_message or ""), seed)
        if deterministic_query:
            result["query"] = deterministic_query
        else:
            result["query"] = result.get("query") or seed.get("query")
        if result.get("result_count") is None and seed.get("result_count") is not None:
            result["result_count"] = seed["result_count"]
        if result.get("currency") is None and seed.get("currency"):
            result["currency"] = seed["currency"]
        if result.get("country") is None and seed.get("country"):
            result["country"] = seed["country"]
        if result.get("site") is None and seed.get("site"):
            result["site"] = seed["site"]
        if seed.get("start_url"):
            result["start_url"] = seed["start_url"]
        elif not result.get("start_url") and result.get("site") in self.KNOWN_SITE_URLS:
            result["start_url"] = self.KNOWN_SITE_URLS[result["site"]]
        if result.get("result_count"):
            result["requires_data_collection"] = True
        return result

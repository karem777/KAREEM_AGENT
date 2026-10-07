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
        # Remove explicit action/website phrases and constraint/output clauses.
        q = text.strip()
        q = re.sub(r"https?://[^\s]+", "", q, flags=re.I)
        q = re.sub(r"(?:افتح|ادخل(?:\s+على)?|روح(?:\s+على)?|خش(?:\s+على)?|open|visit)\s+(?:موقع\s+)?(?:نون|noon|أمازون|امازون|amazon|google|جوجل|github|جيت هب)\b", "", q, flags=re.I)
        q = re.sub(r"(?:أقل من|اقل من|حتى|حد أقصى|under|below|less than)\s*[\d,.]+", "", q, flags=re.I)
        q = re.sub(r"(?:ريال|ر\.س|sar|درهم|aed|د\.إ|جنيه|egp|دولار|usd)\b", "", q, flags=re.I)
        q = re.sub(r"(?:وأظهر|واعرض|اعرض|أظهر|show|list).*$", "", q, flags=re.I)
        q = re.sub(r"(?:أول|اول|first)\s*[0-9٠-٩]*\s*(?:نتائج|نتيجة|results|result)", "", q, flags=re.I)
        q = re.sub(r"(?:بالاسم|والسعر|والرابط|name|price|url|link)", "", q, flags=re.I)
        q = re.sub(r"\s+", " ", q).strip(" ،,؛;.-")
        # Common leading command fragments.
        q = re.sub(r"^(?:ابحث|دور|search|find)\s*(?:عن|على|في|for)?\s*", "", q, flags=re.I)
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
        result["query"] = self._extract_query(str(user_message or ""), result)
        if result.get("result_count") is None and seed.get("result_count") is not None:
            result["result_count"] = seed["result_count"]
        if result.get("currency") is None and seed.get("currency"):
            result["currency"] = seed["currency"]
        if result.get("country") is None and seed.get("country"):
            result["country"] = seed["country"]
        if result.get("site") is None and seed.get("site"):
            result["site"] = seed["site"]
        if result.get("result_count"):
            result["requires_data_collection"] = True
        return result

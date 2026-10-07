from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


class StateReasoner:
    """Reconciles the current world with the user's goal; completion is proof-gated."""

    @staticmethod
    def _origin(url: str) -> str:
        try:
            parsed = urlparse(str(url or "").strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return ""
            return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        except Exception:
            return ""

    REGION_URL_HINTS = {
        "Saudi Arabia": ["saudi-en", ".sa", "/sa/", "saudi-ar"],
        "United Arab Emirates": ["uae-en", ".ae", "/ae/", "dubai"],
        "Egypt": ["egypt", "eg-en", ".eg", "/eg/"],
    }

    def reason(self, goal: dict[str, Any], page: dict[str, Any] | None, history: list[dict[str, Any]]) -> dict[str, Any]:
        page = page or {}
        url = str(page.get("url") or "")
        country = page.get("country")
        currency = page.get("currency")
        required_currency = goal.get("currency")
        required_country = goal.get("country")

        # Infer a regional currency from explicit country URL context when the page
        # text has not exposed a currency symbol yet.
        if not currency and country == "Saudi Arabia":
            currency = "SAR"
        if not currency and country == "United Arab Emirates":
            currency = "AED"

        mismatches: list[str] = []
        if page.get("page_type") == "agent_control_ui" and (goal.get("site") or goal.get("start_url")):
            mismatches.append("agent_control_ui:external_target_required")
        if required_currency and currency and required_currency != currency:
            mismatches.append(f"currency_mismatch:{currency}->{required_currency}")
        if required_country and country and required_country != country:
            mismatches.append(f"country_mismatch:{country}->{required_country}")

        low_url = url.casefold()
        hints = self.REGION_URL_HINTS.get(required_country, []) if required_country else []
        if required_country and hints and url:
            # Only assert a URL mismatch when there is affirmative evidence of another region.
            if required_country == "Saudi Arabia" and any(x in low_url for x in ["uae-en", "/ae/", "dubai", "amazon.ae"]):
                mismatches.append("url_region_mismatch:saudi_required_non_saudi_url")
            elif required_country == "United Arab Emirates" and any(x in low_url for x in ["saudi-en", "/sa/", "amazon.sa"]):
                mismatches.append("url_region_mismatch:uae_required_non_uae_url")

        candidates: list[dict[str, Any]] = []
        llm = page.get("llm") or {}
        if isinstance(llm, dict) and isinstance(llm.get("candidates"), list):
            candidates.extend(c for c in llm["candidates"] if isinstance(c, dict))

        # Use visible result links as secondary candidates so a good page does not
        # depend on the LLM perfectly extracting every object.
        for link in page.get("result_links") or []:
            if not isinstance(link, dict):
                continue
            if not any(str(link.get("url") or "") == str(c.get("url") or "") for c in candidates):
                candidates.append({
                    "name": link.get("name"),
                    "price": None,
                    "currency": currency,
                    "url": link.get("url"),
                    "evidence": link.get("name") or "",
                })

        max_price = (goal.get("constraints") or {}).get("max_price")
        min_price = (goal.get("constraints") or {}).get("min_price")
        query = str(goal.get("query") or "").casefold()
        query_terms = [x for x in re.split(r"[^\w\u0600-\u06FF]+", query) if len(x) >= 2 and x not in {"laptop", "notebook", "لابتوب", "جهاز"}]

        eligible: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for raw in candidates:
            item = dict(raw)
            url_value = str(item.get("url") or "").strip()
            if url_value and url_value in seen_urls:
                continue
            if url_value:
                seen_urls.add(url_value)
            price = item.get("price")
            try:
                price_num = float(str(price).replace(",", "").replace("ر.س", "").replace("SAR", "").strip()) if price is not None else None
            except Exception:
                price_num = None
            item_currency = item.get("currency") or currency
            name = str(item.get("name") or "").casefold()
            hay = f"{name} {str(item.get('evidence') or '').casefold()}"
            if query_terms:
                matches = sum(1 for term in query_terms if term in hay)
                query_match = matches >= max(1, min(2, len(query_terms)))
            else:
                query_match = True
            currency_ok = not required_currency or item_currency == required_currency
            price_ok = True
            if max_price is not None:
                price_ok = price_num is not None and price_num <= float(max_price)
            if min_price is not None:
                price_ok = price_ok and price_num is not None and price_num >= float(min_price)
            fields_ok = bool(item.get("name") and item.get("url"))
            item.update({"price_num": price_num, "eligible": bool(currency_ok and price_ok and query_match and fields_ok)})
            if item["eligible"]:
                eligible.append(item)

        required_count = int(goal.get("result_count") or (1 if goal.get("requires_first_result") else 0))
        # Action goals take precedence over incidental candidate extraction.
        # For "open/click the first result", seeing one eligible candidate on the
        # search page is NOT completion; the agent must actually open it.
        successful_clicks = [
            h for h in history[-30:]
            if isinstance(h, dict)
            and h.get("role") == "tool"
            and h.get("tool") == "browser"
            and h.get("action") == "click"
            and bool((h.get("result") or {}).get("success"))
        ]
        successful_click = bool(successful_clicks)
        click_destination = ""
        if successful_clicks:
            click_destination = str(
                (successful_clicks[-1].get("result") or {}).get("clicked_url")
                or (successful_clicks[-1].get("result") or {}).get("actual_url")
                or ""
            ).strip()
        current_origin = self._origin(url)
        destination_origin = self._origin(click_destination)
        first_result_reached = bool(successful_click and current_origin) and bool(
            not destination_origin or current_origin == destination_origin
        )
        if goal.get("requires_first_result"):
            complete = bool(first_result_reached) and page.get("page_type") not in {"search_home", "search_results"}
        elif goal.get("requires_data_collection"):
            complete = len(eligible) >= max(1, required_count)
        elif goal.get("requires_search"):
            complete = page.get("page_type") == "search_results"
        else:
            complete = False

        if mismatches:
            status = "wrong_context"
        elif complete:
            status = "complete"
        elif page.get("page_type") == "login":
            status = "blocked_auth"
        elif page.get("page_type") == "search_results":
            if goal.get("requires_first_result"):
                status = "results_ready"
            else:
                status = "collecting" if goal.get("requires_data_collection") else "results_ready"
        elif page.get("page_type") == "search_home" or page.get("search_fields"):
            status = "ready_for_search"
        elif page:
            status = "needs_navigation_or_inspection"
        else:
            status = "needs_navigation_or_inspection"

        missing: list[str] = []
        if required_country and not country:
            missing.append("current_country_unknown")
        if required_currency and not currency:
            missing.append("current_currency_unknown")
        if goal.get("requires_data_collection") and len(eligible) < max(1, required_count):
            missing.append(f"eligible_results:{len(eligible)}/{max(1, required_count)}")
        if required_count and len(candidates) < required_count:
            missing.append(f"observed_candidates:{len(candidates)}/{required_count}")

        next_hints: list[str] = []
        if "agent_control_ui:external_target_required" in mismatches:
            next_hints.append("The current page is KAREEM_AGENT itself. Re-bind to the external target URL before any fill/click/type action.")
        elif mismatches:
            next_hints.append("Inspect the current page for a regional/currency selector or another target URL; do not repeat discovery blindly.")
        elif status == "needs_navigation_or_inspection":
            next_hints.append("Navigate to or inspect the current target page before acting.")
        elif status == "ready_for_search":
            next_hints.append("Fill the actual search field with the semantic query only.")
        elif status == "results_ready" and goal.get("requires_first_result"):
            next_hints.append("Open the first organic result now; do not mark the task complete while still on the Google results page.")
        elif status == "collecting":
            next_hints.append("Extract candidates and evidence; scroll or open additional result pages only if more qualifying rows are needed.")
        elif status == "blocked_auth":
            next_hints.append("Stop and request user authentication if credentials are required.")

        return {
            "status": status,
            "complete": bool(complete),
            "goal_relevance": float((page.get("llm") or {}).get("goal_relevance") or (1.0 if page else 0.0)),
            "mismatches": mismatches,
            "eligible_candidates": eligible[:20],
            "candidate_count": len(eligible),
            "observed_candidate_count": len(candidates),
            "missing": missing,
            "next_hints": next_hints,
            "evidence": {
                "url": url,
                "domain": urlparse(url).netloc.lower() if url else "",
                "page_type": page.get("page_type"),
                "country": country,
                "currency": currency,
                "candidate_count": len(eligible),
                "fingerprint": page.get("fingerprint"),
            },
        }

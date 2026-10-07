from __future__ import annotations

import re
from typing import Any


class StateReasoner:
    """Deterministic goal-vs-world reconciliation.

    The model may describe ambiguity, but proof of progress/completion is
    calculated from observed page state and extracted evidence.
    """

    def reason(self, goal: dict[str, Any], page: dict[str, Any] | None, history: list[dict[str, Any]]) -> dict[str, Any]:
        page = page or {}
        url = str(page.get("url") or "")
        country = page.get("country")
        currency = page.get("currency")
        required_currency = goal.get("currency")
        required_country = goal.get("country")

        mismatches: list[str] = []
        if required_currency and currency and required_currency != currency:
            mismatches.append(f"currency_mismatch:{currency}->{required_currency}")
        if required_country and country and required_country != country:
            mismatches.append(f"country_mismatch:{country}->{required_country}")
        low_url = url.casefold()
        if required_country == "Saudi Arabia" and any(x in low_url for x in ["uae-en", "/ae/", "dubai"]):
            mismatches.append("url_region_mismatch:saudi_required_non_saudi_url")

        candidates = []
        llm = page.get("llm") or {}
        if isinstance(llm, dict) and isinstance(llm.get("candidates"), list):
            candidates = [c for c in llm["candidates"] if isinstance(c, dict)]

        eligible = []
        max_price = (goal.get("constraints") or {}).get("max_price")
        min_price = (goal.get("constraints") or {}).get("min_price")
        query = str(goal.get("query") or "").casefold()
        query_terms = [x for x in re.split(r"\W+", query) if len(x) >= 2]
        for item in candidates:
            price = item.get("price")
            try:
                price_num = float(str(price).replace(",", "").strip()) if price is not None else None
            except Exception:
                price_num = None
            item_currency = item.get("currency") or currency
            name = str(item.get("name") or "").casefold()
            query_match = not query_terms or all(term in name for term in query_terms if term not in {"laptop", "لابتوب"}) or any(term in name for term in query_terms)
            currency_ok = not required_currency or not item_currency or item_currency == required_currency
            price_ok = True
            if max_price is not None and price_num is not None:
                price_ok = price_num <= float(max_price)
            elif max_price is not None:
                price_ok = False
            if min_price is not None and price_num is not None:
                price_ok = price_ok and price_num >= float(min_price)
            elif min_price is not None:
                price_ok = False
            item = {**item, "price_num": price_num, "eligible": bool(currency_ok and price_ok and query_match)}
            if item["eligible"]:
                eligible.append(item)

        required_count = int(goal.get("result_count") or (1 if goal.get("requires_first_result") else 0))
        complete = False
        if goal.get("requires_data_collection"):
            complete = len(eligible) >= max(1, required_count)
            if not required_count:
                complete = bool(eligible)
        elif goal.get("requires_first_result"):
            complete = page.get("page_type") not in {"search_home", "search_results"} and bool(url)
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
            status = "collecting" if goal.get("requires_data_collection") else "results_ready"
        elif page.get("page_type") == "search_home" or page.get("search_fields"):
            status = "ready_for_search"
        else:
            status = "needs_navigation_or_inspection"

        missing: list[str] = []
        if required_country and not country:
            missing.append("current_country_unknown")
        if required_currency and not currency:
            missing.append("current_currency_unknown")
        if goal.get("requires_data_collection") and len(eligible) < max(1, required_count):
            missing.append(f"eligible_results:{len(eligible)}/{max(1, required_count)}")
        if required_count and any(x.get("price_num") is None for x in candidates[:required_count]):
            missing.append("some_result_prices_unreadable")

        next_hints: list[str] = []
        if mismatches:
            next_hints.append("Resolve country/currency context before searching or collecting results.")
        elif status == "needs_navigation_or_inspection":
            next_hints.append("Navigate to the target site and inspect the page.")
        elif status == "ready_for_search":
            next_hints.append("Fill the page's search field with the semantic query, excluding output constraints.")
        elif status == "results_ready" and goal.get("requires_first_result"):
            next_hints.append("Choose the first actual result in the user's query context, not the first link on the page.")
        elif status == "collecting":
            if len(eligible) < max(1, required_count):
                next_hints.append("Extract visible eligible candidates, then inspect/scroll for more only if needed.")
        elif status == "blocked_auth":
            next_hints.append("Stop and request user authentication if credentials are required.")

        return {
            "status": status,
            "complete": bool(complete),
            "goal_relevance": float((page.get("llm") or {}).get("goal_relevance") or (1.0 if page else 0.0)),
            "mismatches": mismatches,
            "eligible_candidates": eligible[:12],
            "candidate_count": len(eligible),
            "missing": missing,
            "next_hints": next_hints,
            "evidence": {
                "url": url,
                "page_type": page.get("page_type"),
                "country": country,
                "currency": currency,
                "candidate_count": len(eligible),
                "fingerprint": page.get("fingerprint"),
            },
        }

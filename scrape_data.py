import asyncio
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote_plus

import pandas as pd
from playwright.sync_api import sync_playwright


town ="Rome"

def _run_scraper(city=town, checkin="2026-12-15", checkout="2026-12-18",
                 adults=2, currency="EUR", max_load_more=5,
                 out_csv="booking_research_data.csv"):
    # FIX: Jupyter on Windows uses a Selector event loop, which cannot start
    # subprocesses (Playwright needs one). Switch this thread to Proactor.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # FIX: correct search-results URL (the original pointed at the home page)
    url = (
        "https://www.booking.com/searchresults.html?"
        f"ss={quote_plus(city)}&checkin={checkin}&checkout={checkout}"
        f"&group_adults={adults}&no_rooms=1&group_children=0"
        f"&selected_currency={currency}&lang=en-us"
    )
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
            locale="en-US",
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        # Dismiss sign-in popup / cookie banner if present
        for selector in ('[aria-label="Dismiss sign-in info."]',
                         '#onetrust-accept-btn-handler'):
            try:
                btn = page.locator(selector)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

        # FIX: scroll and click "Load more results" to get beyond the first ~25
        for _ in range(max_load_more):
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(1200)
            try:
                more = page.get_by_role("button", name=re.compile("load more results", re.I))
                if more.count() > 0 and more.first.is_visible():
                    more.first.click()
                    page.wait_for_timeout(2500)
                else:
                    break
            except Exception:
                break

        cards = page.locator('[data-testid="property-card"]').all()
        print(f"Found {len(cards)} property cards")

        for card in cards:
            def get_text(selector):
                try:
                    loc = card.locator(selector).first
                    return loc.inner_text().strip() if loc.count() > 0 else None
                except Exception:
                    return None

            title = get_text('[data-testid="title"]')
            try:
                link_loc = card.locator('[data-testid="title-link"]').first
                prop_url = link_loc.get_attribute("href") if link_loc.count() > 0 else None
            except Exception:
                prop_url = None

            neighborhood = get_text('[data-testid="address"]')
            distance = get_text('[data-testid="distance"]')

            # Review block: parse score and count from its full text
            review_block = get_text('[data-testid="review-score"]') or ""
            score_m = re.search(r"\b(\d{1,2}[.,]\d)\b", review_block)
            count_m = re.search(r"([\d.,\s]+)\s+reviews?", review_block, re.I)
            review_score = score_m.group(1).replace(",", ".") if score_m else None
            review_count = re.sub(r"[^\d]", "", count_m.group(1)) if count_m else None

            room_type = get_text('[data-testid="recommended-units"] h4, '
                                 '[data-testid="recommended-units"] span')
            price = get_text('[data-testid="price-and-discounted-price"]')
            taxes = get_text('[data-testid="taxes-and-charges"]')

            card_text = card.inner_text()
            lines = [ln.strip() for ln in card_text.split("\n") if ln.strip()]
            cancellation = next(
                (l for l in lines if "cancellation" in l.lower() or "prepayment" in l.lower()),
                None)
            urgency = next(
                (l for l in lines if "left at this price" in l.lower()
                 or "only " in l.lower() or "booked" in l.lower()),
                None)

            results.append({
                "scraped_at_utc": scraped_at,
                "search_city": city,
                "checkin": checkin,
                "checkout": checkout,
                "adults": adults,
                "currency": currency,
                "property_name": title,
                "neighborhood": neighborhood,
                "distance": distance,
                "review_score": review_score,
                "review_count": review_count,
                "room_type": room_type,
                "displayed_price": price,
                "taxes": taxes,
                "cancellation_terms": cancellation,
                "urgency_text": urgency,
                "property_url": prop_url.split("?")[0] if prop_url else None,
            })

        browser.close()

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.drop_duplicates(subset="property_url").reset_index(drop=True)
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Saved {len(df)} properties to {out_csv}")
    return df


# ---------------------------------------------------------------
# Option A: run from a terminal  ->  python scrape_booking.py
# ---------------------------------------------------------------
if __name__ == "__main__":
    _run_scraper(town, "2026-12-15", "2026-12-18", 2)

# ---------------------------------------------------------------
# Option B: run inside Jupyter (paste this in a notebook cell
# after defining/importing _run_scraper)
# ---------------------------------------------------------------
# with ThreadPoolExecutor(max_workers=1) as executor:
#     df = executor.submit(_run_scraper, "Paris", "2026-12-15", "2026-12-18", 2).result()
# df.head()

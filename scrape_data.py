import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

def _run_scraper(city="Paris", checkin="2026-12-15", checkout="2026-12-18", adults=2):
    url = (
        f"https://booking.com?"
        f"ss={city}&checkin={checkin}&checkout={checkout}&group_adults={adults}&no_rooms=1"
    )
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        try:
            close_btn = page.locator('[aria-label="Dismiss sign-in info."]')
            if close_btn.is_visible():
                close_btn.click()
        except Exception:
            pass

        for _ in range(3):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)

        cards = page.locator('[data-testid="property-card"]').all()
        
        for card in cards:
            def get_text(selector):
                loc = card.locator(selector).first
                return loc.inner_text().strip() if loc.count() > 0 else None

            title = get_text('[data-testid="title"]')
            link_loc = card.locator('[data-testid="title-link"]').first
            prop_url = link_loc.get_attribute("href") if link_loc.count() > 0 else None
            
            neighborhood = get_text('[data-testid="address"]')
            distance = get_text('[data-testid="distance"]')
            review_score = get_text('[data-testid="review-score"] div:first-child')
            review_count = get_text('[data-testid="review-score"] div:nth-child(2)')
            room_type = get_text('[data-testid="recommended-units"] h4, [data-testid="recommended-units"] span')
            price = get_text('[data-testid="price-and-discounted-price"]')
            taxes = get_text('[data-testid="taxes-and-charges"]')
            
            card_text = card.inner_text()
            lines = [line.strip() for line in card_text.split("\n") if line.strip()]
            
            cancellation = next((l for l in lines if "cancellation" in l.lower() or "prepayment" in l.lower()), None)
            urgency = next((l for l in lines if "left at this price" in l.lower() or "only " in l.lower()), None)

            results.append({
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
                "property_url": prop_url.split("?")[0] if prop_url else None
            })

        browser.close()

    df = pd.DataFrame(results)
    df.to_csv("booking_research_data.csv", index=False, encoding="utf-8-sig")
    print(f"Saved {len(df)} properties to booking_research_data.csv")
    return df

# Execute inside a separate thread to bypass Jupyter's Windows event loop restriction
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(_run_scraper, "Paris", "2026-12-15", "2026-12-18", 2)
    df = future.result()

df.head()

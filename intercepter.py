import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright, Playwright, TimeoutError, Response

class Config:
    """Configuration constants for the scraper."""
    RANK_URL = "https://buyin.jinritemai.com/dashboard/merch-picking-hall/rank?btm_ppre=a10091.b24215.c68160.d839440_i16852609794&btm_pre=a10091.b71710.c68160.d839440_i1482933506&btm_show_id=ebf82770-5d02-48ed-9f92-c1a75d6fd2f3&pre_universal_page_params_id=&universal_page_params_id=e0b97666-5e57-41ab-850a-5418bb06acad"
    RANK_API_URL_PART = "pc/leaderboard/center/pmt"
    DETAIL_API_URL_PART = "pc/selection/decision/pack_detail"
    DETAIL_PAGE_URL_TEMPLATE = "https://buyin.jinritemai.com/dashboard/merch-picking-library/merch-promoting?id={}"
    STORAGE_STATE_FILE = Path("storage_state.json")
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    LOGIN_TIMEOUT = 300000  # 5 minutes
    REQUEST_TIMEOUT = 30000  # 30 seconds

INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'en-GB']});
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );
    try {
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
          if (parameter === 37445) { # VENDOR
            return 'Intel Open Source Technology Center';
          }
          if (parameter === 37446) { # RENDERER
            return 'Mesa DRI Intel(R) Ivybridge Mobile ';
          }
          return getParameter(parameter);
        };
    } catch (e) {
        console.log('Could not spoof WebGL');
    }
"""

def _is_rank_data_response(response: Response) -> bool:
    """Check if the response is for the rank data API."""
    return Config.RANK_API_URL_PART in response.url

def _is_detail_core_data_response(response: Response) -> bool:
    """Check if the response is for the detail page core data API."""
    if Config.DETAIL_API_URL_PART not in response.url or response.request.method != "POST":
        return False
    try:
        post_data = response.request.post_data_json
        return post_data.get("data_module") == "core"
    except (json.JSONDecodeError, AttributeError):
        return False

def _is_detail_7day_data_response(response: Response) -> bool:
    """Check if the response is for the detail page 7-day data API."""
    if Config.DETAIL_API_URL_PART not in response.url or response.request.method != "POST":
        return False
    try:
        post_data = response.request.post_data_json
        return (
            post_data.get("data_module") == "dynamic" and
            post_data.get("dynamic_params", {}).get("promotion_data_params", {}).get("time_range") == '7'
        )
    except (json.JSONDecodeError, AttributeError):
        return False

async def get_response_json(response: Response, description: str):
    """Safely get JSON from a response and print it."""
    print(f"\n✅ --- Successfully intercepted {description} ---")
    try:
        data = await response.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"--- End of {description} ---")
        return data
    except json.JSONDecodeError:
        print(f"❌ Could not parse {description} response as JSON.")
        print("Received response text:")
        print(await response.text())
        return None

async def run(playwright: Playwright):
    """Main execution function."""
    storage_state = str(Config.STORAGE_STATE_FILE.absolute()) if Config.STORAGE_STATE_FILE.exists() else None
    if storage_state:
        print(f"Found session file at {Config.STORAGE_STATE_FILE}, attempting to reuse it.")
    else:
        print("No local session file found, proceeding with a new session (may require login).")

    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        storage_state=storage_state,
        user_agent=Config.USER_AGENT
    )
    await context.add_init_script(INIT_SCRIPT)
    page = await context.new_page()

    try:
        print(f"Navigating to rank page: {Config.RANK_URL}")
        await page.goto(Config.RANK_URL, wait_until="domcontentloaded")

        if "login" in page.url:
            print("Login required. Please log in in the browser window.")
            print("Waiting for successful login...")
            await page.wait_for_url(lambda url: "login" not in url, timeout=Config.LOGIN_TIMEOUT)
            print("Login successful. Continuing script.")

        await page.wait_for_timeout(random.randint(1000, 2500))
        print("Clicking '趋势榜' (Trend Rank)...")
        await page.get_by_text("趋势榜", exact=True).click()

        await page.wait_for_timeout(random.randint(1000, 2500))
        
        print("Clicking '短视频' (Short Video) and waiting for rank data...")
        async with page.expect_response(_is_rank_data_response, timeout=Config.REQUEST_TIMEOUT) as response_info:
            await page.get_by_text("短视频", exact=True).click()
        
        rank_response = await response_info.value
        rank_data = await get_response_json(rank_response, "Rank Data")

        promotions = rank_data.get("data", {}).get("promotions") if rank_data else []
        if not promotions:
            print("❌ Could not find 'promotions' in rank data. Cannot proceed.")
            return

        first_product_id = promotions[0].get("product_id")
        if not first_product_id:
            print("❌ Could not find 'product_id' for the first product. Cannot proceed.")
            return

        detail_page_url = Config.DETAIL_PAGE_URL_TEMPLATE.format(first_product_id)
        print(f"Found product ID: {first_product_id}")
        print(f"Navigating to detail page: {detail_page_url}")

        # --- Fetch Core Data ---
        async with page.expect_response(_is_detail_core_data_response, timeout=Config.REQUEST_TIMEOUT) as core_response_info:
            await page.goto(detail_page_url, wait_until="domcontentloaded")
        
        core_response = await core_response_info.value
        await get_response_json(core_response, "Detail Page Core Data")

        # --- Fetch 7-Day Data ---
        print("Clicking '近7天' (Last 7 days) to get 7-day data...")
        try:
            await page.wait_for_load_state('networkidle')
            async with page.expect_response(_is_detail_7day_data_response, timeout=Config.REQUEST_TIMEOUT) as seven_day_response_info:
                await page.get_by_text("近7天", exact=True).click()
            
            seven_day_response = await seven_day_response_info.value
            await get_response_json(seven_day_response, "Detail Page 7-Day Data")

        except TimeoutError:
            print(f"❌ Timed out waiting for 7-day data after clicking '近7天'.")
            print("💡 This might happen if the 7-day data was already loaded by default.")

    except TimeoutError:
        print("❌ Operation timed out. Please check your network or if the page structure has changed.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        print("Saving current session state (cookies, etc.)...")
        await context.storage_state(path=Config.STORAGE_STATE_FILE)
        print(f"Session state saved to: {Config.STORAGE_STATE_FILE}")
        
        await context.close()
        await browser.close()
        print("Browser closed.")


async def main():
    """Async main entry point."""
    async with async_playwright() as playwright:
        await run(playwright)


if __name__ == "__main__":
    print("Starting Playwright data scraping script...")
    try:
        import playwright
    except ImportError:
        print("Error: 'playwright' library not found.")
        print("Please install it via pip: pip install playwright")
        print("And then run: playwright install")
        exit(1)
        
    asyncio.run(main())

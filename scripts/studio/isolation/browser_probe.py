"""Browser-side negative probes, executed only inside the inert Docker runtime."""
import json
from playwright.sync_api import sync_playwright

def main():
    checks = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, chromium_sandbox=True,
            args=["--disable-background-networking", "--disable-component-update"])
        page = browser.new_page()
        page.set_content("<h1>Synthetic isolation canary</h1>")
        checks["synthetic_page_rendered"] = page.locator("h1").inner_text() == "Synthetic isolation canary"
        checks["screenshot"] = len(page.screenshot()) > 100
        checks["fetch_denied"] = page.evaluate("""async () => {
            try { await fetch('http://192.0.2.1:8123', {signal:AbortSignal.timeout(2000)}); return false; }
            catch { return true; }
        }""")
        try:
            page.goto("http://192.0.2.1:8123",timeout=2500)
            checks["navigation_denied"] = False
        except Exception:
            checks["navigation_denied"] = True
        browser.close()
    print(json.dumps({"passed":all(checks.values()),"checks":checks}))

if __name__ == "__main__":
    main()

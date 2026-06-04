from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:8080/accounts/login/')
    page.fill("input[name='username']", "testowner@kliniassist.app")
    page.fill("input[name='password']", "testpass123")
    page.click("button:has-text('Sign In')")
    page.wait_for_load_state("networkidle")
    print("URL after login:", page.url)
    print("Title:", page.title())
    content = page.content()
    if "error" in content.lower() or "invalid" in content.lower():
        print("Error found in page")
    if "dashboard" in content.lower():
        print("Dashboard content found")
    if "csrf" in content.lower():
        print("CSRF token present")
    browser.close()

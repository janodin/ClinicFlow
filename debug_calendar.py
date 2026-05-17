from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Collect console logs
    logs = []
    page.on("console", lambda msg: logs.append(f"{msg.type}: {msg.text}"))
    page.on("pageerror", lambda err: logs.append(f"PAGE ERROR: {err}"))

    # Login
    page.goto("http://127.0.0.1:8080/accounts/login/")
    page.fill("input[name='username']", "testowner@clinicflow.com")
    page.fill("input[name='password']", "testpass123")
    page.click("button:has-text('Sign In')")
    page.wait_for_load_state("networkidle")
    print("URL after login:", page.url)

    # Go to calendar
    page.goto("http://127.0.0.1:8080/calendar/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    print("URL on calendar:", page.url)
    print("Title:", page.title())

    # Check for FullCalendar
    fc = page.locator("#calendar").count()
    print("Calendar div count:", fc)
    fc_el = page.locator(".fc").count()
    print(".fc elements:", fc_el)

    # Screenshot
    page.screenshot(path="calendar_debug.png", full_page=True)
    print("Screenshot saved to calendar_debug.png")

    print("\nConsole logs:")
    for log in logs:
        print(log)

    browser.close()

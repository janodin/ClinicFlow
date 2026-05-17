import pytest
import os
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.mark.django_db(transaction=True)
def test_full_guest_booking_flow(live_server, page, clinic_setup):
    clinic, service = clinic_setup
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()

    # Navigate to public booking page
    url = live_server.url + reverse("public_booking:book", args=[clinic.slug])
    page.goto(url)

    # Wait for initial slots to load via HTMX (init() triggers loadSlots)
    page.wait_for_selector("[data-testid='slot-button']", state="attached", timeout=5000)

    # Step 1: Select service
    page.select_option("#service-select", value=str(service.id))
    page.wait_for_selector("[data-testid='slot-button']", state="attached", timeout=5000)
    page.click("[data-testid='continue-button-step1']")

    # Step 2: Select date and time slot
    with page.expect_response(lambda resp: "slots" in resp.url, timeout=5000):
        page.select_option("#date-select", value=tomorrow)
    page.wait_for_selector("[data-testid='slot-button']", state="attached", timeout=5000)
    page.click("[data-testid='slot-button']")
    page.click("[data-testid='continue-button-step2']")

    # Step 3: Enter patient details
    page.fill("[data-testid='full-name-input']", "Test Patient")
    page.fill("[data-testid='phone-input']", "09171234567")
    page.fill("[data-testid='email-input']", "test@example.com")
    page.click("[data-testid='review-button-step3']")

    # Step 4: Review & Confirm
    expect(page.locator("text=Review & Confirm")).to_be_visible()
    page.click("[data-testid='confirm-button-step4']")

    # Step 5: Success page with reference code
    page.wait_for_selector("text=Booking Confirmed!", timeout=5000)
    expect(page.locator("text=Reference Code")).to_be_visible()
    ref_code = page.inner_text("[data-testid='reference-code']")
    assert ref_code.startswith("CF-")
    assert len(ref_code) == 11  # "CF-" + 8 chars

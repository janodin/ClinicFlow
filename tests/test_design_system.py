from pathlib import Path
import re


CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "css" / "kliniassist.css"
DASHBOARD_BASE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "base.html"
DASHBOARD_HOME_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "home.html"
SEARCH_RESULTS_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "partials" / "search_results.html"
ROOT = Path(__file__).resolve().parents[1]
PARTIALS_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "partials"


def css_text():
    return CSS_PATH.read_text(encoding="utf-8")


def css_media_block(query):
    css = css_text()
    marker = f"@media ({query}) {{"
    start = css.index(marker)
    body_start = start + len(marker)
    depth = 1
    index = body_start
    while index < len(css):
        char = css[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return css[body_start:index]
        index += 1
    raise AssertionError(f"Could not find closing brace for {marker}")


def dashboard_base_text():
    return DASHBOARD_BASE_PATH.read_text(encoding="utf-8")


def dashboard_home_text():
    return DASHBOARD_HOME_PATH.read_text(encoding="utf-8")


def search_results_text():
    return SEARCH_RESULTS_PATH.read_text(encoding="utf-8")


def source_text(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_visible_brand_copy_uses_kliniassist():
    brand_files = [
        "config/settings.py",
        "accounts/forms.py",
        "clinics/forms.py",
        "templates/base.html",
        "templates/accounts/login.html",
        "templates/accounts/signup.html",
        "templates/accounts/onboarding.html",
        "templates/dashboard/base.html",
        "templates/dashboard/assistant_settings.html",
        "templates/privacy_policy.html",
        "templates/widget/widget.html",
        "templates/emails/base_email.html",
    ]

    combined = "\n".join(source_text(path) for path in brand_files)

    legacy_brand = "Clinic" + "Flow"

    assert "KliniAssist" in combined
    assert legacy_brand not in combined


def test_active_frontend_technical_namespace_uses_kliniassist():
    active_files = [
        "templates/base.html",
        "templates/dashboard/assistant_settings.html",
        "templates/widget/widget.html",
        "widget/views.py",
    ]
    combined = "\n".join(source_text(path) for path in active_files)
    legacy_prefix = "clinic" + "flow"

    assert (ROOT / "static" / "css" / "kliniassist.css").exists()
    assert not (ROOT / "static" / "css" / f"{legacy_prefix}.css").exists()
    assert "css/kliniassist.css" in combined
    assert "kliniassist-widget-frame" in combined
    assert "kliniassist-minimize" in combined
    assert "kliniassist:load-slots" in combined
    assert f"{legacy_prefix}.css" not in combined
    assert f"{legacy_prefix}-widget-frame" not in combined
    assert f"{legacy_prefix}-minimize" not in combined
    assert f"{legacy_prefix}:load-slots" not in combined


def div_block_containing(template, marker):
    marker_index = template.index(marker)
    start = template.rfind("<div", 0, marker_index)
    depth = 0
    for match in re.finditer(r"<(/?)div\b[^>]*>", template[start:], re.IGNORECASE):
        if match.group(1):
            depth -= 1
            if depth == 0:
                return template[start : start + match.end()]
        else:
            depth += 1
    raise AssertionError(f"Could not find containing div for {marker}")


def tag_block_containing(template, tag, marker):
    marker_index = template.index(marker)
    start = template.rfind(f"<{tag}", 0, marker_index + len(marker))
    assert start != -1, f"Could not find opening <{tag}> before {marker}"
    depth = 0
    for match in re.finditer(rf"<(/?){tag}\b[^>]*>", template[start:], re.IGNORECASE | re.DOTALL):
        if match.group(1):
            depth -= 1
            if depth == 0:
                block = template[start : start + match.end()]
                assert marker in block, f"Returned <{tag}> block does not contain {marker}"
                return block
        else:
            depth += 1
    raise AssertionError(f"Could not find containing {tag} for {marker}")


def tag_block_after(template, tag, marker):
    marker_index = template.index(marker)
    start = template.index(f"<{tag}", marker_index)
    depth = 0
    for match in re.finditer(rf"<(/?){tag}\b[^>]*>", template[start:], re.IGNORECASE | re.DOTALL):
        if match.group(1):
            depth -= 1
            if depth == 0:
                return template[start : start + match.end()]
        else:
            depth += 1
    raise AssertionError(f"Could not find {tag} after {marker}")


def opening_tag_containing(template, tag, marker):
    marker_index = template.index(marker)
    for match in re.finditer(rf"<{tag}\b[^>]*>", template, re.IGNORECASE | re.DOTALL):
        if match.start() <= marker_index < match.end():
            return match.group(0)
    start = template.rfind(f"<{tag}", 0, marker_index)
    assert start != -1, f"Could not find opening <{tag}> before {marker}"
    end = template.index(">", start) + 1
    opening = template[start:end]
    assert marker in opening, f"Returned <{tag}> opening tag does not contain {marker}"
    return opening


def class_tokens_from_value(class_value):
    return set(class_value.split())


def class_tokens_from_markup(markup):
    match = re.search(r'\bclass="([^"]*)"', markup)
    assert match is not None, f"Could not find class attribute in {markup[:120]}"
    return class_tokens_from_value(match.group(1))


def assert_class_tokens(tokens, *expected):
    missing = [token for token in expected if token not in tokens]
    assert not missing, f"Missing class tokens {missing} from {sorted(tokens)}"


def assert_not_class_token_group(tokens, *unexpected):
    assert not all(token in tokens for token in unexpected), (
        f"Unexpected class token group {unexpected} found in {sorted(tokens)}"
    )


def legacy_utility_patterns(*, include_font_weight=False):
    patterns = [
        f"text-{'slate'}-",
        f"bg-{'slate'}-",
        f"border-{'slate'}-",
        f"bg-{'cyan'}-",
        f"text-{'cyan'}-",
        f"border-{'cyan'}-",
        f"focus:border-{'cyan'}",
        f"focus:ring-{'cyan'}",
    ]
    if include_font_weight:
        patterns.append("font-[850]")
    return patterns


def partial_text(name):
    return (PARTIALS_PATH / name).read_text(encoding="utf-8")


CF_BTN_TEMPLATE_PATHS = [
    "templates/dashboard/appointments.html",
    "templates/dashboard/calendar.html",
    "templates/dashboard/patients.html",
    "templates/dashboard/services.html",
    "templates/dashboard/home.html",
    "templates/dashboard/settings.html",
    "templates/dashboard/unavailable_dates.html",
    "templates/dashboard/slot_preview.html",
    "templates/dashboard/business_hours.html",
    "templates/dashboard/assistant_settings.html",
    "templates/dashboard/voice_agent.html",
    "dashboard/templates/dashboard/messenger_settings.html",
    "templates/dashboard/partials/appointment_detail.html",
    "templates/dashboard/partials/appointment_form.html",
    "templates/dashboard/partials/appointment_list.html",
    "templates/dashboard/partials/appointment_row.html",
    "templates/dashboard/partials/patient_detail_content.html",
    "templates/dashboard/partials/patient_edit_modal_form.html",
    "templates/dashboard/partials/add_patient_modal.html",
    "templates/dashboard/partials/patient_row.html",
    "templates/dashboard/partials/patient_list.html",
    "templates/dashboard/partials/service_form.html",
    "templates/dashboard/partials/service_row.html",
    "templates/dashboard/partials/service_list.html",
    "templates/dashboard/partials/faq_row.html",
    "templates/dashboard/partials/duplicate_list.html",
    "templates/dashboard/partials/merge_confirm.html",
    "templates/dashboard/partials/merge_success.html",
    "templates/accounts/login.html",
    "templates/accounts/signup.html",
    "templates/accounts/password_reset.html",
    "templates/accounts/password_reset_done.html",
    "templates/accounts/password_reset_confirm.html",
    "templates/accounts/password_reset_complete.html",
    "templates/widget/widget.html",
    "templates/widget/booking_success.html",
    "templates/widget/partials/booking_success.html",
    "templates/widget/partials/booking_error.html",
]

CF_BTN_TAG_RE = re.compile(
    r"<(?P<tag>a|button)\b(?P<attrs>[^>]*\bclass=\"[^\"]*\bcf-btn\b[^\"]*\"[^>]*)>"
    r"(?P<body>.*?)</(?P=tag)>",
    re.DOTALL,
)
HTML_TAG_RE = re.compile(r"<[^>]+>")
TEMPLATE_TAG_RE = re.compile(r"{[%{#].*?[#}%]}", re.DOTALL)
INLINE_DISPLAY_NONE_ELEMENT_RE = re.compile(
    r"<(?P<tag>[a-z][\w:-]*)\b[^>]*\bstyle=\"[^\"]*display\s*:\s*none[^\"]*\"[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)


def visible_button_text(body):
    text = HTML_TAG_RE.sub(" ", body)
    text = TEMPLATE_TAG_RE.sub(" ", text)
    return " ".join(text.split())


def visible_button_icon_body(body):
    return INLINE_DISPLAY_NONE_ELEMENT_RE.sub("", body)


def test_labeled_cf_buttons_include_supplemental_lucide_icons():
    missing = []
    for relative_path in CF_BTN_TEMPLATE_PATHS:
        template = source_text(relative_path)
        for match in CF_BTN_TAG_RE.finditer(template):
            body = match.group("body")
            label = visible_button_text(body)
            if not label or not re.search(r"[A-Za-z]", label):
                continue
            if "data-lucide=" not in visible_button_icon_body(body):
                missing.append(f"{relative_path}: {label}")

    assert missing == []


def test_public_auth_and_widget_button_labels_preserve_original_casing():
    expected_label_snippets = {
        "templates/accounts/login.html": [">Sign In</button>"],
        "templates/accounts/signup.html": [">Create Account</button>"],
        "templates/widget/widget.html": [">Continue</button>", ">Confirm Appointment</button>"],
        "templates/widget/booking_success.html": [">Book Another Appointment</a>"],
        "templates/widget/partials/booking_success.html": [">Book Another Appointment</a>"],
        "templates/widget/partials/booking_error.html": [">Back to Booking</a>"],
    }

    for relative_path, snippets in expected_label_snippets.items():
        template = source_text(relative_path)
        for snippet in snippets:
            assert snippet in template


def test_signup_terms_checkbox_uses_inline_soft_consent_row():
    template = source_text("templates/accounts/signup.html")

    assert "field.name == 'terms_accepted'" in template
    assert "rounded-[var(--cf-radius-md)] border border-[var(--cf-line)] bg-[var(--cf-surface-muted)]" in template
    assert "m-0 flex items-center gap-3 cursor-pointer" in template
    assert "grid h-5 shrink-0 place-items-center" in template
    assert "text-sm font-medium leading-5 text-[var(--cf-muted)]" in template
    assert "mt-0.5 shrink-0" not in template


def test_global_checkboxes_use_custom_neon_aqua_control():
    css = css_text()
    checkbox = css_rule_block('input[type="checkbox"]')
    checked = css_rule_block('input[type="checkbox"]:checked')
    focus = css_rule_block('input[type="checkbox"]:focus-visible')
    disabled = css_rule_block('input[type="checkbox"]:disabled')

    assert "appearance: none;" in checkbox
    assert "-webkit-appearance: none;" in checkbox
    assert "width: 1.25rem;" in checkbox
    assert "height: 1.25rem;" in checkbox
    assert "border: 1.5px solid var(--cf-input-line);" in checkbox
    assert "border-radius: var(--cf-radius-sm);" in checkbox
    assert "background-color: var(--cf-surface);" in checkbox
    assert "background-color: var(--cf-brand);" in checked
    assert "stroke='%23ffffff'" in checked
    assert "box-shadow: 0 0 0 3px var(--cf-focus);" in focus
    assert "cursor: not-allowed;" in disabled
    assert ".cf-checkbox { accent-color: var(--cf-brand); }" not in css


def test_mobile_responsive_css_has_shared_baseline_contracts():
    css = css_text()
    mobile_break = css_rule_block(".cf-mobile-break")
    scroll_hint = css_rule_block(".cf-mobile-scroll-hint")
    table_scroll_hint = css_rule_block(".cf-table-scroll::after")
    secret_toggle = css_rule_block(".cf-secret-toggle")
    auth_panel_after = css_rule_block(".cf-auth-panel::after")
    mobile_block = css_media_block("max-width: 640px")
    page_actions_mobile = re.search(r"(?ms)^\s*\.cf-page-actions\s*\{(?P<body>.*?)^\s*\}", mobile_block)
    topbar_search_panel_mobile = re.search(
        r"(?ms)^\s*\.cf-topbar-search \.cf-search-panel\s*\{(?P<body>.*?)^\s*\}",
        mobile_block,
    )

    assert css_rule_block(".cf-page-header > :first-child") is not None
    assert "min-width: 0;" in mobile_break
    assert "overflow-wrap: anywhere;" in mobile_break
    assert "word-break: break-word;" in mobile_break
    assert "color: var(--cf-muted);" in scroll_hint
    assert "background: linear-gradient(90deg, transparent, var(--cf-surface));" in table_scroll_hint
    assert "width: 2.5rem;" in secret_toggle
    assert "min-height: 2.5rem;" in secret_toggle
    assert "pointer-events: none;" in auth_panel_after
    assert ".cf-sticky-action-col" not in css
    assert page_actions_mobile is not None
    assert "width: 100%;" in page_actions_mobile.group("body")
    assert "align-items: stretch;" in page_actions_mobile.group("body")
    assert topbar_search_panel_mobile is not None
    assert "position: fixed;" in topbar_search_panel_mobile.group("body")
    assert ".cf-row-actions .cf-btn-xs" in mobile_block
    assert "min-height: 2.75rem;" in mobile_block
    assert "min-height: 2.5rem;" in mobile_block
    assert re.search(r"(?m)^\s*\.cf-faq-icon-action\s*\{", mobile_block) is not None


def test_mobile_dashboard_shell_contracts():
    template = dashboard_base_text()
    overlay_start = template.index("<!-- Mobile overlay -->")
    overlay_end = template.index("<aside", overlay_start)
    overlay_block = template[overlay_start:overlay_end]
    sidebar_opening = re.search(r"<aside\b(?P<attrs>[^>]*)>", template, re.DOTALL)
    assert sidebar_opening is not None
    sidebar_attrs = sidebar_opening.group("attrs")
    sidebar_tokens = class_tokens_from_markup(sidebar_attrs)
    sidebar_end = template.index("</aside>", sidebar_opening.start()) + len("</aside>")
    sidebar_block = template[sidebar_opening.start() : sidebar_end]
    sidebar_nav = re.search(r"<nav\b(?P<attrs>[^>]*)>", sidebar_block, re.DOTALL)
    assert "z-[45]" in overlay_block
    assert_not_class_token_group(sidebar_tokens, "-translate-x-full", "lg:translate-x-0")
    assert "sidebarOpen || isDesktop" in sidebar_attrs
    assert sidebar_nav is not None
    assert_class_tokens(class_tokens_from_markup(sidebar_nav.group("attrs")), "pb-safe")

    nav_start = template.index("<!-- Bottom mobile nav -->")
    nav_end = template.index("</nav>", nav_start) + len("</nav>")
    bottom_nav_block = template[nav_start:nav_end]
    assert "fixed bottom-0" in bottom_nav_block
    for label in ["Overview", "Appts", "Calendar", "Patients", "Services", "More"]:
        nav_label = tag_block_containing(bottom_nav_block, "span", f">{label}<")
        assert_class_tokens(class_tokens_from_markup(nav_label), "block", "max-w-full", "truncate")

    settings_href = "{% url 'dashboard:settings' %}"
    settings_href_index = bottom_nav_block.index(settings_href)
    settings_anchor_start = bottom_nav_block.rfind("<a ", 0, settings_href_index)
    settings_anchor_end = bottom_nav_block.index("</a>", settings_href_index) + len("</a>")
    settings_anchor = bottom_nav_block[settings_anchor_start:settings_anchor_end]
    assert settings_href in settings_anchor
    assert ">More</span>" in settings_anchor


def test_mobile_more_nav_marks_yakap_as_setup_active():
    template = dashboard_base_text()
    nav_start = template.index("<!-- Bottom mobile nav -->")
    nav_end = template.index("</nav>", nav_start) + len("</nav>")
    bottom_nav_block = template[nav_start:nav_end]

    settings_href = "{% url 'dashboard:settings' %}"
    settings_href_index = bottom_nav_block.index(settings_href)
    settings_anchor_start = bottom_nav_block.rfind("<a ", 0, settings_href_index)
    settings_anchor_end = bottom_nav_block.index("</a>", settings_href_index) + len("</a>")
    settings_anchor = bottom_nav_block[settings_anchor_start:settings_anchor_end]

    assert "request.resolver_match.url_name == 'yakap'" in settings_anchor


def test_mobile_responsive_page_specific_contracts():
    home = source_text("templates/dashboard/home.html")
    appointment_list = partial_text("appointment_list.html")
    appointment_row = partial_text("appointment_row.html")
    appointment_detail = partial_text("appointment_detail.html")
    patient_row = partial_text("patient_row.html")
    patient_detail = partial_text("patient_detail_content.html")
    yakap = source_text("templates/dashboard/yakap.html")
    css = css_text()
    tablet_css = css_media_block("max-width: 768px")
    calendar_card = re.search(r"(?ms)^\s*\.cf-calendar-card\s*\{(?P<body>.*?)^\s*\}", tablet_css)
    home_header_copy = div_block_containing(home, "Today at {{ clinic.name }}")
    home_title = tag_block_containing(home_header_copy, "h1", "Today at {{ clinic.name }}")
    appointment_patient_cell = tag_block_containing(appointment_row, "td", "{{ appointment.patient.full_name }}")
    appointment_service_cell = tag_block_containing(appointment_row, "td", "{{ appointment.service.name }}")
    appointment_detail_patient_card = div_block_containing(appointment_detail, "{{ appointment.patient.full_name }}")
    patient_identity_link = tag_block_containing(patient_row, "a", "{{ patient.full_name }}")
    patient_identity_name = tag_block_containing(patient_identity_link, "span", "max-w-[14rem]")
    patient_header_identity = div_block_containing(patient_detail, '<span class="grid h-14')
    yakap_verification_section = tag_block_containing(yakap, "section", "Start here: verify before service so the clinic does not absorb uncovered YAKAP usage.")
    yakap_ledger_section = tag_block_containing(yakap, "section", "Latest manual estimated usage, adjustments, and reversals for this clinic.")
    yakap_ledger_table = opening_tag_containing(yakap_ledger_section, "table", "cf-table-wide")

    assert 'class="min-w-0"' in home_header_copy
    assert_class_tokens(class_tokens_from_markup(home_title), "cf-page-title", "ui-page-title", "cf-mobile-break")
    assert "cf-mobile-scroll-hint" in appointment_list
    assert "cf-mobile-break" in appointment_patient_cell
    assert "cf-mobile-break" in appointment_service_cell
    assert "min-w-0" in appointment_detail_patient_card
    assert_class_tokens(class_tokens_from_markup(patient_identity_name), "max-w-[14rem]", "break-all")
    assert_class_tokens(
        class_tokens_from_markup(patient_header_identity),
        "flex",
        "flex-col",
        "items-start",
        "gap-3",
        "sm:flex-row",
    )
    for table in re.findall(r"<table\b[^>]*>", yakap_verification_section):
        assert_not_class_token_group(class_tokens_from_markup(table), "cf-table", "cf-table-compact")
    assert_class_tokens(class_tokens_from_markup(yakap_ledger_table), "cf-table", "cf-table-wide")
    assert '<th class="p-4">Type</th>' in yakap_ledger_section
    assert "{{ entry.get_entry_type_display }}" in yakap_ledger_section
    assert calendar_card is not None
    assert "height: auto;" in calendar_card.group("body")
    assert "overflow: visible;" in calendar_card.group("body")
    assert "@media (pointer: coarse) {" in css
    pointer_coarse_css = css_media_block("pointer: coarse")
    assert "#calendar .fc-event" in pointer_coarse_css
    assert "min-height: 2.5rem;" in pointer_coarse_css


def test_yakap_dashboard_prioritizes_daily_work_before_admin_tools():
    template = source_text("templates/dashboard/yakap.html")

    verification_index = template.index("YAKAP review queue")
    risk_index = template.index("Patient-category estimates with positive remaining coverage at or below the clinic threshold.")
    ledger_index = template.index("Recent YAKAP ledger entries")
    settings_index = template.index("YAKAP Policy Settings")
    categories_index = template.index("YAKAP Categories")

    assert verification_index < risk_index < ledger_index
    assert ledger_index < settings_index < categories_index
    assert "Manual ledger export" not in template
    assert "Export CSV" not in template
    assert "Services needing YAKAP setup" not in template
    assert "Classify active services so staff and booking flows show consistent estimates." not in template
    assert "Review status" in template
    assert "Ask a settings manager" in template


def test_yakap_modal_refocuses_after_htmx_content_swap():
    template = source_text("templates/dashboard/yakap.html")
    modal_start = template.rindex('<div x-show="detailOpen"')
    modal = template[modal_start:]

    assert "focusModal(root)" in template
    assert "@htmx:after-swap.window" in modal
    assert "$event.target.id === 'detail-modal-body'" in modal


def test_yakap_categories_table_uses_modal_edit_actions():
    template = source_text("templates/dashboard/yakap.html")
    section_start = template.index("YAKAP Categories")
    modal_start = template.index('<div x-show="detailOpen"')
    section = template[section_start:modal_start]

    assert "Edit Category Limits" not in section
    assert '<th class="p-4">Action</th>' in section
    assert "editingCategoryId" in template
    assert "categoryEditOpen" in template
    assert "editingCategoryId = {{ category.id }}; categoryEditOpen = true" in section
    assert "categoryEditOpen" in section
    assert "cf-modal-backdrop" in section
    assert "Edit YAKAP category" in section
    assert 'name="category_id" value="{{ category.id }}"' in section
    assert '<tr x-show="editingCategoryId === {{ category.id }}"' not in section


def test_yakap_categories_table_uses_modal_add_action():
    template = source_text("templates/dashboard/yakap.html")
    section_start = template.index("YAKAP Categories")
    modal_start = template.index('<div x-show="detailOpen"')
    section = template[section_start:modal_start]

    assert '<h2 class="cf-section-title">Coverage Categories</h2>' not in template
    assert '<h2 class="cf-section-title">YAKAP Categories</h2>' in template
    assert '<h2 class="cf-section-title">Current YAKAP Categories</h2>' not in template
    assert "categoryCreateOpen" in template
    assert "categoryCreateOpen = true" in section
    assert "Manage the benefit categories used for YAKAP estimates. Staff can review limits here; settings managers can add or edit categories." in section
    assert "Add category" in section
    assert section.index("Add category") < section.index("{{ categories|length }} categories")
    assert "Add YAKAP category" in section
    assert 'name="_form" value="category"' in section
    create_title = section.index("Add YAKAP category")
    create_form_start = section.rfind("<form", 0, create_title)
    create_form_end = section.index("</form>", create_title)
    create_form = section[create_form_start:create_form_end]
    assert 'name="category_id"' not in create_form


def test_calendar_mobile_viewport_contracts():
    template = source_text("templates/dashboard/calendar.html")
    css = css_text()
    mobile_css = css_media_block("max-width: 640px")

    assert "calendarScreen = window.matchMedia('(max-width: 768px)')" in template
    assert "calendarCoarsePointer = window.matchMedia('(pointer: coarse)')" in template
    assert "const isPhone = () => calendarScreen.matches;" in template
    assert "const isCoarsePointer = () => calendarCoarsePointer.matches;" in template
    assert "initialView: 'dayGridMonth'" in template
    assert "initialView: isPhone() ? 'timeGridDay' : 'dayGridMonth'" not in template
    assert "calendar.changeView('timeGridDay')" not in template
    assert "syncCalendarViewport" in template
    assert "calendar.setOption('height', phone ? 'auto' : '100%')" in template
    assert "calendar.setOption('dayMaxEvents', phone ? 2 : 5)" in template
    assert "calendar.updateSize();" in template
    assert "calendarScreen.addEventListener('change', syncCalendarViewport)" in template
    assert "calendarScreen.addListener(syncCalendarViewport)" in template
    assert "window.addEventListener('orientationchange'" in template
    assert "window.setTimeout(syncCalendarViewport, 150)" in template
    assert "data-calendar-view=\"dayGridMonth\"" in template
    assert "data-calendar-view=\"timeGridWeek\"" in template
    assert "data-calendar-view=\"timeGridDay\"" in template
    assert "data-calendar-desktop-view" not in template
    assert "cf-calendar-desktop-view" not in template
    assert ".cf-calendar-view-button[aria-pressed=\"true\"]" in css
    assert ".cf-calendar-view-button[aria-pressed=\"false\"]" in css
    assert ".cf-calendar-grid-scroll" in css
    assert "min-width: 42rem;" in mobile_css


def test_calendar_responsive_css_collapses_header_filters_and_safe_month_scroll():
    css = css_text()
    tablet_css = css_media_block("max-width: 768px")
    mobile_css = css_media_block("max-width: 640px")

    card = css_rule_block(".cf-calendar-card")
    scroll = css_rule_block(".cf-calendar-grid-scroll")
    title = css_rule_block(".cf-calendar-title")
    legend_badge = css_rule_block(".cf-calendar-legend-badge")
    time_label = css_rule_block("#calendar .fc-timegrid-slot-label")
    time_event = css_rule_block("#calendar .fc-timegrid-event")

    assert "height: calc(100dvh - 15rem);" in card
    assert "min-height: 32rem;" in card
    assert "overflow: hidden;" in scroll
    assert "font-weight: 400;" in title
    assert "position: relative;" in legend_badge
    assert "font-variant-numeric: tabular-nums;" in time_label
    assert "border-radius: var(--cf-radius-sm);" in time_event
    assert "height: auto;" in tablet_css
    assert "min-height: 0;" in tablet_css
    assert "overflow: visible;" in tablet_css
    assert ".cf-calendar-header" in tablet_css
    assert "grid-template-columns: 1fr;" in tablet_css
    assert "#calendar.cf-calendar-grid-scroll" in tablet_css
    assert ".cf-calendar-grid-scroll" in tablet_css
    assert "overflow: auto;" in tablet_css
    assert "min-width: 44rem;" in tablet_css
    assert "#calendar .fc-dayGridMonth-view .fc-scroller" in tablet_css
    assert ".cf-calendar-title" in mobile_css
    assert "height: auto;" in mobile_css
    assert "min-height: 0;" in mobile_css
    assert "overflow: visible;" in mobile_css
    assert "white-space: normal;" in mobile_css
    assert "overflow-wrap: anywhere;" in mobile_css
    assert "min-width: 42rem;" in mobile_css


def test_calendar_interaction_contracts_for_loading_active_views_and_touch_drag():
    template = source_text("templates/dashboard/calendar.html")

    assert "id=\"calendar-today\" aria-pressed=\"false\" class=\"cf-btn cf-btn-sm cf-calendar-view-button\"" in template
    assert "const todayButton = document.getElementById('calendar-today');" in template
    assert "function syncCalendarTodayButton(view)" in template
    assert "const active = view.currentStart <= today && today < view.currentEnd;" in template
    assert "todayButton.setAttribute('aria-pressed', active ? 'true' : 'false');" in template
    assert "todayButton.classList.toggle('cf-calendar-view-active', active);" in template
    assert "syncCalendarTodayButton(info.view);" in template
    assert "aria-pressed=\"true\"" in template
    assert "aria-pressed=\"false\"" in template
    assert "syncCalendarViewButtons(info.view.type);" in template
    assert "button.setAttribute('aria-pressed', active ? 'true' : 'false');" in template
    assert "button.classList.toggle('cf-calendar-view-active', active);" in template
    assert "loading: function(isLoading)" in template
    assert "setCalendarBusy(isLoading);" in template
    assert "showCalendarError('Calendar events could not be loaded. Please try again.');" in template
    assert "eventAllow: function(dropInfo, draggedEvent)" in template
    assert "return isCalendarEventEditable(draggedEvent);" in template
    assert "editable: !isCoarsePointer()" in template
    assert "calendarCoarsePointer.addEventListener('change', syncCalendarEditability)" in template
    assert "calendarCoarsePointer.addListener(syncCalendarEditability)" in template
    assert "showCalendarDetailError" in template
    assert "htmx:responseError" in template
    assert "htmx:sendError" in template


def test_appointments_mobile_filter_and_sticky_action_contracts():
    template = source_text("templates/dashboard/appointments.html")
    list_template = source_text("templates/dashboard/partials/appointment_list.html")
    row_template = source_text("templates/dashboard/partials/appointment_row.html")
    css = css_text()
    mobile_css = css_media_block("max-width: 640px")

    assert "filtersOpen" in template
    assert "cf-advanced-filters" in template
    assert "cf-mobile-filter-toggle" in template
    assert "aria-controls=\"appointment-advanced-filters\"" in template
    assert "id=\"appointment-advanced-filters\"" in template
    assert ".cf-mobile-filter-toggle { display: none; }" in css
    assert ".cf-mobile-filter-toggle { display: inline-flex; }" in mobile_css
    assert "cf-sticky-action-col" not in list_template
    assert "cf-sticky-action-col" not in row_template
    assert "cf-row-actions cf-appointment-row-actions" in row_template
    assert "cf-appointment-view-action" in row_template
    assert "cf-btn-danger" in row_template


def test_patient_and_service_mobile_contracts():
    patients = source_text("templates/dashboard/patients.html")
    add_patient = source_text("templates/dashboard/partials/add_patient_modal.html")
    patient_detail = source_text("templates/dashboard/partials/patient_detail_content.html")
    patient_list = source_text("templates/dashboard/partials/patient_list.html")
    patient_row = source_text("templates/dashboard/partials/patient_row.html")
    service_row = source_text("templates/dashboard/partials/service_row.html")
    services = source_text("templates/dashboard/services.html")
    duplicate_list = source_text("templates/dashboard/partials/duplicate_list.html")

    assert "trapModalFocus" in patients
    assert "focusModal(root)" in patients
    assert "@keydown.tab=\"trapModalFocus($event, $el)\"" in patients
    assert "x-effect=\"if (editOpen) focusModal($el)\"" in patients
    assert "@htmx:after-swap.window=\"if (editOpen && $event.target.id === 'edit-modal-body') focusModal($el)\"" in patients
    assert "trapModalFocus" in add_patient
    assert "cf-mobile-break" in patient_detail
    assert "cf-sticky-action-col" not in patient_list
    assert "cf-sticky-action-col" not in patient_row
    assert "cf-row-actions" in patient_list
    assert "cf-row-actions" in patient_row
    assert "cf-appointment-view-action" in patient_list
    assert "cf-service-edit-action" in patient_list
    assert "<div class=\"cf-row-actions shrink-0\">" in duplicate_list
    assert "class=\"cf-btn cf-btn-sm cf-btn-primary\"" in duplicate_list
    assert "cf-row-actions hidden" not in duplicate_list
    assert "cf-btn-sm sm:cf-btn-xs" not in service_row
    assert "cf-row-actions" in service_row
    assert "cf-mobile-break" in service_row
    assert "w-full sm:w-auto" in services
    assert "focusModal(root)" in services
    assert "@htmx:after-swap.window=\"if (editModalOpen && $event.target.id === 'edit-modal-body') focusModal($el)\"" in services
    assert "x-effect=\"if (open) focusModal($el)\"" in services
    assert "x-effect=\"if (editModalOpen) focusModal($el)\"" in services


def test_auth_public_and_widget_mobile_contracts():
    login = source_text("templates/accounts/login.html")
    signup = source_text("templates/accounts/signup.html")
    onboarding = source_text("templates/accounts/onboarding.html")
    privacy = source_text("templates/privacy_policy.html")
    widget = source_text("templates/widget/widget.html")
    widget_success = source_text("templates/widget/partials/booking_success.html")
    widget_error = source_text("templates/widget/partials/booking_error.html")
    widget_views = source_text("widget/views.py")

    assert "min-h-dvh" in login
    assert "items-start sm:items-center" in login
    assert "min-h-dvh" in signup
    assert "min-h-11" in signup
    assert "min-h-dvh" in onboarding
    assert "env(safe-area-inset-bottom)" in onboarding
    assert "{% extends \"base.html\" %}" in privacy
    assert "cf-policy-shell" in privacy
    assert "cf-widget-scroll" in widget
    assert "autocomplete=\"name\"" in widget
    assert "autocomplete=\"tel\"" in widget
    assert "break-all" in widget_success
    assert "break-words" in widget_error
    assert "@media (max-width: 640px)" in widget_views


def test_settings_public_widget_mobile_hardening_contracts():
    settings = source_text("templates/dashboard/settings.html")
    business_hours = source_text("templates/dashboard/business_hours.html")
    assistant_settings = source_text("templates/dashboard/assistant_settings.html")
    messenger_settings = source_text("dashboard/templates/dashboard/messenger_settings.html")
    widget_embed = source_text("templates/dashboard/widget_embed.html")
    onboarding = source_text("templates/accounts/onboarding.html")
    widget_success = source_text("templates/widget/booking_success.html")
    widget = source_text("templates/widget/widget.html")
    auth_panel_after = css_rule_block(".cf-auth-panel::after")
    settings_break_cell = tag_block_containing(settings, "td", "settings-break-start-{{ weekday }}")
    business_hours_break_cell = tag_block_containing(business_hours, "td", 'name="break_start_{{ weekday }}"')
    provider_status = opening_tag_containing(assistant_settings, "span", "data-ai-provider-model-status")
    model_option_class = re.search(r"button\.className = '(?P<class>[^']+)';", assistant_settings)
    messenger_app_secret_toggle = opening_tag_containing(messenger_settings, "button", 'data-secret-field="app_secret"')
    messenger_page_token_toggle = opening_tag_containing(messenger_settings, "button", 'data-secret-field="page_access_token"')
    messenger_meta_callback_label = '<p class="cf-label">Meta Callback URL</p>'
    messenger_n8n_worker_label = '<p class="cf-label">n8n Worker Webhook URL</p>'
    messenger_django_webhook_label = '<p class="cf-label">Django Webhook URL</p>'
    messenger_meta_callback_field = div_block_containing(messenger_settings, messenger_meta_callback_label)
    messenger_n8n_worker_field = div_block_containing(messenger_settings, messenger_n8n_worker_label)
    messenger_django_webhook_field = div_block_containing(messenger_settings, messenger_django_webhook_label)
    messenger_meta_callback_row = tag_block_after(messenger_meta_callback_field, "div", messenger_meta_callback_label)
    messenger_n8n_worker_row = tag_block_after(messenger_n8n_worker_field, "div", messenger_n8n_worker_label)
    messenger_django_webhook_row = tag_block_after(messenger_django_webhook_field, "div", messenger_django_webhook_label)
    widget_script_pre = opening_tag_containing(widget_embed, "pre", 'id="script-code"')
    widget_iframe_pre = opening_tag_containing(widget_embed, "pre", 'id="iframe-code"')
    onboarding_title = tag_block_containing(onboarding, "h1", "Complete {{ clinic.name }} setup")
    onboarding_hours_section = tag_block_containing(onboarding, "section", "Business Hours")
    widget_scroll = opening_tag_containing(widget, "div", "cf-widget-scroll")
    widget_chat_pane = opening_tag_containing(widget, "div", 'x-show="mode===\'chat\'"')
    widget_chat_conversation_pane = opening_tag_containing(widget, "div", 'x-show="chatTab===\'conversation\'"')
    widget_chat_faqs_pane = opening_tag_containing(widget, "div", 'x-show="chatTab===\'faqs\'"')
    widget_faq_question = opening_tag_containing(widget, "span", 'x-text="faq.question"')
    widget_faq_answer = opening_tag_containing(widget, "div", 'x-text="faq.answer"')

    for break_cell in [settings_break_cell, business_hours_break_cell]:
        break_cell_tokens = class_tokens_from_markup(break_cell)
        assert_class_tokens(break_cell_tokens, "p-4")
        assert "min-w-[14rem]" in break_cell
        assert_not_class_token_group(break_cell_tokens, "p-4", "flex", "gap-2")
    assert_class_tokens(
        class_tokens_from_markup(provider_status),
        "whitespace-normal",
        "break-words",
        "text-left",
        "leading-snug",
    )
    assert model_option_class is not None
    assert_class_tokens(class_tokens_from_value(model_option_class.group("class")), "break-words", "whitespace-normal")
    for secret_toggle in [messenger_app_secret_toggle, messenger_page_token_toggle]:
        secret_toggle_tokens = class_tokens_from_markup(secret_toggle)
        assert_class_tokens(secret_toggle_tokens, "h-10", "w-10")
        assert_not_class_token_group(secret_toggle_tokens, "h-8", "w-8")
    for webhook_row in [messenger_meta_callback_row, messenger_n8n_worker_row, messenger_django_webhook_row]:
        copy_button = tag_block_containing(webhook_row, "button", "copy-label")
        webhook_row_opening = opening_tag_containing(webhook_row, "div", "max-sm:flex-col")
        assert_class_tokens(class_tokens_from_markup(webhook_row_opening), "max-sm:flex-col", "max-sm:items-stretch")
        assert_class_tokens(class_tokens_from_markup(copy_button), "w-full", "sm:w-auto")
    for pre in [widget_script_pre, widget_iframe_pre]:
        pre_tokens = class_tokens_from_markup(pre)
        assert_class_tokens(pre_tokens, "pr-4", "sm:pr-24")
        assert "pr-24" not in pre_tokens
    assert "cf-mobile-scroll-hint" in onboarding_hours_section
    assert_class_tokens(class_tokens_from_markup(onboarding_title), "cf-mobile-break")
    assert "min-h-dvh" in widget_success
    for widget_pane in [widget_scroll, widget_chat_pane, widget_chat_conversation_pane, widget_chat_faqs_pane]:
        assert_class_tokens(class_tokens_from_markup(widget_pane), "min-h-0")
    assert_class_tokens(class_tokens_from_markup(widget_faq_question), "break-words")
    assert_class_tokens(class_tokens_from_markup(widget_faq_answer), "cf-mobile-break")
    assert "pointer-events: none;" in auth_panel_after


def test_password_reset_templates_follow_auth_shell_contract():
    login = source_text("templates/accounts/login.html")
    signup = source_text("templates/accounts/signup.html")
    reset_templates = [
        "templates/accounts/password_reset.html",
        "templates/accounts/password_reset_done.html",
        "templates/accounts/password_reset_confirm.html",
        "templates/accounts/password_reset_complete.html",
    ]

    assert "{% url 'accounts:password_reset' %}" in login
    assert "{% url 'accounts:password_reset' %}" not in signup

    for relative_path in reset_templates:
        template = source_text(relative_path)
        assert "{% extends \"base.html\" %}" in template
        assert "cf-auth-panel" in template
        assert "cf-card" in template
        assert "cf-btn cf-btn-primary" in template


def test_widget_mobile_embed_contracts_are_specific():
    widget = source_text("templates/widget/widget.html")
    partial_success = source_text("templates/widget/partials/booking_success.html")
    full_success = source_text("templates/widget/booking_success.html")
    widget_error = source_text("templates/widget/partials/booking_error.html")
    widget_embed = source_text("templates/dashboard/widget_embed.html")
    widget_views = source_text("widget/views.py")
    chat_option_button = opening_tag_containing(widget, "button", 'x-text="opt.label"')

    assert "flex min-w-0 items-center gap-3" in widget
    assert "shrink-0 rounded-full" in widget
    assert "<div class=\"min-w-0\">" in widget
    assert "<h1 class=\"max-w-full truncate" in widget
    assert "name=\"phone\" type=\"tel\" required autocomplete=\"tel\"" in widget
    assert "name=\"email\" type=\"email\" required autocomplete=\"email\"" in widget
    assert "x-model=\"collectInfo.phone\"" in widget
    assert "type=\"tel\" autocomplete=\"tel\"" in widget
    assert "x-model=\"collectInfo.email\"" in widget
    assert "type=\"email\" autocomplete=\"email\"" in widget
    assert "accentForeground()" in widget
    assert "background-color:' + accentColor + '; color:' + accentForeground()" in widget
    assert "min-h-10 flex-1 rounded-lg" in widget
    assert_class_tokens(class_tokens_from_markup(chat_option_button), "min-h-10", "rounded-xl", "border", "break-words")
    assert "min-h-11 w-full rounded-xl" in widget
    assert "min-h-11 min-w-11" in widget
    assert "text-white text-sm font-black\" style=\"background-color: {{ clinic.safe_widget_accent_color }}" not in widget
    assert "break-all" in partial_success
    assert "break-all" in full_success
    assert "text-white\" style=\"background-color: {{ clinic.safe_widget_accent_color }}" not in partial_success
    assert "text-white\" style=\"background-color: {{ clinic.safe_widget_accent_color }}" not in full_success
    assert "cf-btn cf-btn-primary mt-4 w-full\" style=\"background-color: {{ clinic.safe_widget_accent_color }}" not in partial_success
    assert "cf-btn cf-btn-primary mt-4 w-full\" style=\"background-color: {{ clinic.safe_widget_accent_color }}" not in full_success
    assert "border-[var(--cf-danger)]" in widget_error
    assert "bg-[var(--cf-danger-soft)]" in widget_error
    assert "text-[var(--cf-danger)]" in widget_error
    assert "relative h-[420px] overflow-hidden" in widget_embed
    assert "sm:h-[520px]" in widget_embed
    assert "class=\"h-full w-full\" style=\"border:none;\"" in widget_embed
    assert "kliniassist-widget-frame" in widget_views
    assert "@media (max-width: 640px)" in widget_views


def test_widget_header_controls_use_system_hover_treatment():
    widget = source_text("templates/widget/widget.html")
    css = css_text()

    assert '@click="goHome()" class="cf-widget-header-control min-h-10 min-w-10 rounded-xl"' in widget
    assert '@click="minimize()" class="cf-widget-header-control min-h-10 min-w-10 rounded-xl"' in widget

    control = css_rule_block(".cf-widget-header-control")
    assert "display: inline-grid;" in control
    assert "border: 1px solid transparent;" in control
    assert "color: currentColor;" in control

    hover = css_rule_block(".cf-widget-header-control:hover,\n.cf-widget-header-control:focus-visible")
    assert "background: rgba(255, 255, 255, .22);" in hover
    assert "border-color: rgba(255, 255, 255, .38);" in hover
    assert "transform: translateY(-1px);" in hover

    assert re.search(
        r"(?m)^\.cf-widget-header-control:focus-visible\s*\{\s*\n"
        r"\s*outline: none;\s*\n"
        r"\s*box-shadow: 0 0 0 3px var\(--cf-focus\), var\(--cf-shadow-subtle\);",
        css,
    )


def css_rule_block(selector):
    css = css_text()
    match = re.search(rf"(?m)^{re.escape(selector)}\s*\{{(?P<body>.*?)^\}}", css, re.DOTALL)
    if match is None:
        selector_pattern = r"\s*,\s*".join(re.escape(part.strip()) for part in selector.split(","))
        match = re.search(rf"(?m)^{selector_pattern}\s*\{{(?P<body>.*?)^\}}", css, re.DOTALL)
    if match is None and "," not in selector:
        selector_pattern = rf"{re.escape(selector)}(?=\s*(?:,|\{{))(?:\s*,\s*[^{{]+)?"
        match = re.search(rf"(?m)^{selector_pattern}\s*\{{(?P<body>.*?)^\}}", css, re.DOTALL)
    if match is None:
        match = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{(?P<body>.*?)^\s*\}}", css, re.DOTALL)
    assert match is not None
    return match.group("body")


def test_css_uses_neon_aqua_tokens_and_typography():
    css = css_text().lower()

    expected_tokens = [
        "--cf-brand: #06b6d4",
        "--cf-brand-hover: #0891b2",
        "--cf-brand-strong: #0e7490",
        "--cf-dashboard-dark: #052f3a",
        "--cf-ink: #083344",
        "--cf-muted: #527486",
        "--cf-bg: #ffffff",
        "--cf-bg-strong: #f0fdff",
        "--cf-surface-warm: #f0fdff",
        "--cf-line: #d5f3f8",
        "--cf-input-line: #8ed8e8",
        "--cf-focus: rgba(6, 182, 212, .24)",
    ]
    for token in expected_tokens:
        assert token in css

    assert "family=inter:wght@300;400;500;600;700;800" in css
    assert "font-family: \"inter\", sans-serif;" in css
    assert "font-feature-settings: \"ss01\";" in css
    assert "font-variant-numeric: tabular-nums;" in css
    assert "cormorant garamond" not in css
    assert "manrope" not in css
    assert "ibm plex mono" not in css


def test_css_avoids_stone_sage_fonts_and_raw_legacy_colors():
    css = css_text().lower()

    forbidden = [
        "font-weight: 850",
        "font-weight: 750",
        "#0f6b55",
        "#eef5f8",
        "#" + "365449",
        "#" + "243a33",
        "#" + "2e493f",
        "#" + "ebe7dd",
        "#" + "f8f6ef",
        "#533afd",
        "#4434d4",
        "#2e2b8c",
        "#1c1e54",
        "#ededff",
        "stone-sage",
        "cormorant",
        "manrope",
        "ibm plex mono",
    ]
    for value in forbidden:
        assert value not in css


def test_css_contains_canonical_controls_and_field_states():
    css = css_text()

    for selector in [
        ".cf-page",
        ".cf-page-header",
        ".cf-page-title",
        ".cf-page-description",
        ".cf-page-actions",
        ".cf-async-panel:empty",
        ".cf-btn",
        ".cf-btn-primary",
        ".cf-btn-secondary",
        ".cf-btn-ghost",
        ".cf-btn-danger",
        ".cf-btn-link",
        ".cf-btn-sm",
        ".cf-btn-lg",
        ".cf-icon-btn",
        ".cf-field",
        ".cf-label",
        ".cf-input",
        ".cf-select",
        ".cf-textarea",
        ".cf-help",
        ".cf-error",
    ]:
        assert selector in css

    assert ".cf-label" in css
    assert "color: var(--cf-muted);" in css
    assert ".cf-icon-btn" in css
    assert "background: transparent;" in css
    for snippet in [
        "input:disabled",
        "select:disabled",
        "textarea:disabled",
        ".cf-input:disabled",
        ".cf-select:disabled",
        ".cf-textarea:disabled",
        ".ui-input:disabled",
        "background-color: var(--cf-surface-muted);",
        "cursor: not-allowed;",
        "opacity: 1;",
    ]:
        assert snippet in css


def test_css_uses_neon_aqua_component_geometry():
    css = css_text()
    button = css_rule_block(".cf-btn")
    card = css_rule_block(".cf-card")
    input_block = css_rule_block("input,\nselect,\ntextarea,\n.cf-input,\n.cf-select,\n.cf-textarea")

    assert "border-radius: var(--cf-radius-pill);" in button
    assert "font-weight: 400;" in button
    assert "border-radius: var(--cf-radius-lg);" in card
    assert "box-shadow: var(--cf-shadow-card);" in card
    assert "border-color: var(--cf-input-line);" in input_block or "border: 1px solid var(--cf-input-line);" in input_block


def test_compact_textarea_uses_short_settings_height():
    css = css_text()
    compact = css_rule_block(".cf-textarea-compact")

    assert "min-height: 4.5rem;" in compact


def test_outline_buttons_keep_brand_hover_state():
    css = css_text()
    hover_block = css_rule_block(".cf-btn-secondary:hover,\n.ui-button-secondary:hover")

    assert "background: var(--cf-brand-soft);" in hover_block
    assert "border-color: var(--cf-brand-hover);" in hover_block
    assert "color: var(--cf-brand-hover);" in hover_block

    for match in re.finditer(r"(?ms)^[^{]*cf-btn-secondary:hover[^{]*\{(?P<body>.*?)^\}", css):
        assert "var(--cf-surface-warm)" not in match.group("body")


def test_danger_buttons_are_filled_not_outline():
    danger_button = css_rule_block(".cf-btn-danger")
    danger_hover = css_rule_block(".cf-btn-danger:hover")

    assert "border-color: var(--cf-danger);" in danger_button
    assert "background: var(--cf-danger);" in danger_button
    assert "color: #fff;" in danger_button
    assert "var(--cf-danger-soft)" not in danger_button
    assert "background: var(--cf-danger-soft);" not in danger_hover


def test_css_contains_cards_tables_and_badges():
    css = css_text()

    for selector in [
        ".cf-card",
        ".cf-card-muted",
        ".cf-kpi",
            ".cf-table-wrap",
            ".cf-table-scroll",
            ".cf-table-header",
            ".cf-table",
        ".cf-row-actions",
        ".cf-badge",
    ]:
        assert selector in css

    table_wrap = css_rule_block(".cf-table-wrap")
    table_scroll = css_rule_block(".cf-table-scroll")
    assert "overflow: hidden;" in table_wrap
    assert "overflow-x: auto;" in table_scroll
    assert "overflow-y: hidden;" in table_scroll


def test_active_badges_use_electric_aqua_theme_not_completed_status():
    css = css_text()
    active_badge = css_rule_block(".cf-badge-active")

    assert "background: var(--cf-brand);" in active_badge
    assert "color: #fff;" in active_badge
    assert "var(--cf-brand-strong)" not in active_badge
    assert "var(--cf-status-completed-bg)" not in active_badge
    assert "var(--cf-status-completed-text)" not in active_badge

    active_badge_template_paths = [
        "templates/dashboard/billing.html",
        "templates/dashboard/partials/service_row.html",
        "templates/dashboard/partials/patient_row.html",
        "templates/dashboard/partials/patient_list.html",
        "templates/dashboard/slot_preview.html",
        "dashboard/templates/dashboard/messenger_settings.html",
    ]
    for relative_path in active_badge_template_paths:
        template = source_text(relative_path)
        assert "cf-badge-active" in template

    assert "cf-status-confirmed\">Active" not in source_text("templates/dashboard/partials/patient_row.html")
    assert "cf-status-confirmed\">Active" not in source_text("templates/dashboard/partials/patient_list.html")
    assert "bg-[var(--cf-status-completed-bg)]" not in source_text("templates/dashboard/billing.html")
    assert "bg-[var(--cf-status-completed-bg)]" not in source_text("templates/dashboard/partials/service_row.html")


def test_visible_active_labels_include_check_circle_icon():
    expected_snippets = {
        "templates/dashboard/billing.html": [
            '<i data-lucide="check-circle-2" class="h-5 w-5" aria-hidden="true"></i>{{ clinic.group.get_status_display }}',
        ],
        "templates/dashboard/partials/service_row.html": [
            '<i data-lucide="check-circle-2" class="h-3 w-3" aria-hidden="true"></i> Active',
            '<i data-lucide="x-circle" class="h-3 w-3" aria-hidden="true"></i> Inactive',
        ],
        "templates/dashboard/partials/patient_row.html": [
            '<i data-lucide="check-circle-2" class="h-3 w-3" aria-hidden="true"></i> Active',
        ],
        "templates/dashboard/partials/patient_list.html": [
            '<i data-lucide="check-circle-2" class="h-3 w-3" aria-hidden="true"></i> Active',
        ],
        "dashboard/templates/dashboard/messenger_settings.html": [
            '<i data-lucide="check-circle-2" class="h-3 w-3" aria-hidden="true"></i> Connected',
        ],
        "templates/dashboard/services.html": [
            '<i data-lucide="check-circle-2" class="h-3.5 w-3.5" aria-hidden="true"></i>Active</button>',
        ],
        "templates/dashboard/home.html": [
            '<i data-lucide="check-circle-2" class="h-3.5 w-3.5 text-[var(--cf-brand)]" aria-hidden="true"></i>Active clinic:',
            '<i data-lucide="check-circle-2" class="h-5 w-5 text-[var(--cf-brand)]" aria-hidden="true"></i>Active</div>',
        ],
    }

    for relative_path, snippets in expected_snippets.items():
        template = source_text(relative_path)
        for snippet in snippets:
            assert snippet in template


def test_css_contains_readable_dropdown_select_rules():
    css = css_text()

    for snippet in [
        "select option",
        "select option:disabled",
        "select option:checked",
        "select[multiple]",
        ".cf-menu-panel",
        ".cf-search-panel",
        ".cf-menu-row",
        ".cf-search-result",
        "background: #fff;",
        "color: var(--cf-muted);",
        "background: var(--cf-brand-soft);",
        "color: var(--cf-brand-strong);",
    ]:
        assert snippet in css


def test_css_contains_status_modal_and_toast_classes():
    css = css_text()

    for selector in [
        ".cf-status-pending",
        ".cf-status-booked",
        ".cf-status-confirmed",
        ".cf-status-completed",
        ".cf-status-cancelled",
        ".cf-status-no-show",
        ".cf-status-no_show",
        ".cf-modal-backdrop",
        ".cf-modal",
        ".cf-modal-sm",
        ".cf-modal-md",
        ".cf-modal-lg",
        ".cf-modal-xl",
        ".cf-modal-header",
        ".cf-modal-title",
        ".cf-modal-description",
        ".cf-modal-body",
        ".cf-modal-footer",
        ".cf-toast-container",
        ".cf-toast",
        ".cf-toast-success",
        ".cf-toast-error",
        ".cf-toast-warning",
        ".cf-toast-info",
        ".cf-toast-icon",
        ".cf-toast-message",
        ".cf-toast-close",
    ]:
        assert selector in css


def test_toasts_use_accessible_design_tokens_and_safe_layering():
    css = css_text()
    root = css_rule_block(":root")
    container = css_rule_block(".cf-toast-container")
    toast = css_rule_block(".cf-toast")
    close = css_rule_block(".cf-toast-close")
    warning = css_rule_block(".cf-toast-warning")
    info = css_rule_block(".cf-toast-info")

    assert "--cf-z-modal: 90;" in root
    assert "--cf-z-toast: 100;" in root
    assert root.index("--cf-z-modal: 90;") < root.index("--cf-z-toast: 100;")
    assert "bottom: 1.5rem;" in container
    assert "top: 6rem;" not in container
    assert "align-items: center;" in toast
    assert "align-items: flex-start;" not in toast
    assert "border: 1px solid var(--cf-line);" in toast
    assert "border-radius: var(--cf-radius-lg);" in toast
    assert "background: var(--cf-surface);" in toast
    assert "padding: .5rem .75rem;" in toast
    assert "padding: .875rem 1rem;" not in toast
    assert "font-weight: 500;" in toast
    assert "width: 2.5rem;" in close
    assert "height: 2.5rem;" in close
    assert "background: transparent;" in close
    assert "background: color-mix(in srgb, currentColor 12%, transparent);" not in close
    assert ".cf-toast-success { background: var(--cf-brand-soft);" in css
    assert ".cf-toast-error { background: var(--cf-danger-soft);" in css
    assert ".cf-toast-warning { background: var(--cf-warning-soft);" in css
    assert ".cf-toast-info { background: var(--cf-info-soft);" in css
    assert "color: var(--cf-ink);" in info
    assert "color: var(--cf-ink);" in warning

    mobile = re.search(r"@media \(max-width: 640px\) \{(?P<body>.*?)^\}", css, re.DOTALL | re.MULTILINE).group("body")
    assert "top: calc(var(--cf-topbar-height) + env(safe-area-inset-top) + .75rem);" in mobile
    assert "bottom: auto;" in mobile


def test_css_contains_widget_sizing_and_mobile_safe_margins():
    css = css_text()

    for snippet in [
        ".cf-widget-shell",
        "width: var(--cf-widget-width);",
        "height: var(--cf-widget-height);",
        "max-width: min(var(--cf-widget-width), calc(100vw - 24px));",
        "max-height: min(var(--cf-widget-height), calc(100dvh - 24px));",
        "border-radius: var(--cf-radius-lg);",
        "max-width: calc(100vw - 24px);",
        "max-height: calc(100dvh - 24px);",
    ]:
        assert snippet in css


def test_css_scopes_mobile_table_width_and_keeps_slot_text_readable():
    css = css_text()

    assert re.search(r"(?m)^\s*table\s*\{\s*min-width:\s*720px;\s*\}", css) is None
    assert "min-width: max(100%, 44rem);" in css_rule_block(".cf-table")
    assert ".cf-slot-button" in css
    slot_button = css_rule_block(".cf-slot-button")
    assert "color: var(--cf-ink);" in slot_button
    assert "cursor: pointer;" in slot_button


def test_active_ui_sources_do_not_depend_on_legacy_design_aliases():
    css = css_text()
    legacy_patterns = [
        f"text-{'cyan'}-",
        f"bg-{'cyan'}-",
        f"border-{'cyan'}-",
        f"border-{'slate'}-",
        f"focus:border-{'cyan'}",
        f"focus:ring-{'cyan'}",
        "font-[850]",
    ]

    for selector in [".ui-page-title", ".ui-input"]:
        assert selector in css

    for pattern in legacy_patterns:
        assert pattern not in css

    for relative_path in [
        "templates/dashboard/base.html",
        "templates/dashboard/home.html",
        "templates/dashboard/appointments.html",
        "templates/dashboard/calendar.html",
        "templates/dashboard/patients.html",
        "templates/widget/widget.html",
        "templates/widget/partials/slots.html",
        "templates/accounts/login.html",
        "templates/accounts/signup.html",
        "accounts/forms.py",
        "clinics/forms.py",
    ]:
        source = source_text(relative_path)
        for pattern in legacy_patterns:
            assert pattern not in source


def test_dashboard_sidebar_uses_neon_aqua_shell_treatment():
    css = css_text()
    sidebar = css_rule_block(".cf-sidebar")
    hover = css_rule_block(".cf-nav-link:hover")
    active = css_rule_block(".cf-nav-link-active")

    assert "linear-gradient(180deg, #0f667c 0%, #0b7f99 54%, #0c5f58 100%)" in sidebar
    assert "radial-gradient(circle at 18% 0%, rgba(165, 243, 252, .28), transparent 15rem)" in sidebar
    assert "border-right: 1px solid rgba(34, 211, 238, .22);" in sidebar
    assert "box-shadow: inset -1px 0 0 rgba(165, 243, 252, .18), 10px 0 28px rgba(8, 51, 68, .12);" in sidebar
    assert "color: rgba(207, 250, 254, .76) !important;" in css
    assert "background: rgba(5, 47, 58, .18);" in hover
    assert "border-color: rgba(125, 211, 252, .22);" in hover
    assert "background: linear-gradient(90deg, rgba(5, 47, 58, .34), rgba(8, 145, 178, .18));" in active
    assert "box-shadow: inset 3px 0 0 var(--cf-brand), 0 0 20px rgba(6, 182, 212, .16);" in active


def test_dashboard_pages_use_canonical_page_header_anatomy():
    page_paths = [
        "templates/dashboard/home.html",
        "templates/dashboard/appointments.html",
        "templates/dashboard/calendar.html",
        "templates/dashboard/patients.html",
        "templates/dashboard/services.html",
        "templates/dashboard/settings.html",
        "templates/dashboard/unavailable_dates.html",
        "templates/dashboard/slot_preview.html",
        "templates/dashboard/business_hours.html",
        "templates/dashboard/widget_embed.html",
        "templates/dashboard/assistant_settings.html",
        "templates/dashboard/billing.html",
        "templates/dashboard/profile.html",
        "dashboard/templates/dashboard/messenger_settings.html",
    ]

    for path in page_paths:
        template = source_text(path)
        assert "class=\"cf-page" in template
        assert "cf-page-header" in template
        assert "cf-page-title ui-page-title" in template
        assert "cf-page-description" in template
        header_region = div_block_containing(template, "cf-page-header")
        assert "cf-eyebrow" not in header_region
        assert re.search(r'class="[^"]*\bcf-page-title\b[^"]*\bmt-', header_region) is None
        assert re.search(r'class="[^"]*\bcf-page-description\b[^"]*\bmt-', header_region) is None
        assert "text-[var(--cf-muted)]" not in header_region
        assert "text-sm text-[var(--cf-muted)]" not in header_region


def test_profile_page_contains_password_change_card():
    template = source_text("templates/dashboard/profile.html")

    assert "Change password" in template
    assert "password_form.old_password" in template
    assert "password_form.new_password1" in template
    assert "password_form.new_password2" in template
    assert "cf-btn cf-btn-primary" in template
    assert "cf-error" in template


def test_messenger_connection_left_with_setup_and_webhook_stacked_on_right():
    template = source_text("dashboard/templates/dashboard/messenger_settings.html")
    css = css_text()

    setup_row_start = template.index("<!-- Messenger Setup Row -->")
    ai_prompt_heading_start = template.index("Shared Assistant")
    ai_prompt_start = template.rindex('<section class="cf-card p-6">', 0, ai_prompt_heading_start)
    setup_row = template[setup_row_start:ai_prompt_start]

    assert 'class="grid gap-5 lg:grid-cols-2"' in setup_row
    assert '<div class="grid gap-5">\n  <!-- Instructions Card -->' in setup_row
    assert setup_row.index("Facebook Page Connection") < setup_row.index("Setup Instructions")
    assert setup_row.index("Setup Instructions") < setup_row.index("n8n Webhook")
    assert setup_row.count("cf-card p-6") == 3

    connection_start = setup_row.index("<!-- Connection Status Card -->")
    right_column_start = setup_row.index('<div class="grid gap-5">')
    connection_card = setup_row[connection_start:right_column_start]
    header_start = connection_card.index("cf-messenger-connection-header")
    header_end = connection_card.index('<form id="messenger-connection-form"')
    connection_header = connection_card[header_start:header_end]

    assert "sm:justify-between" in connection_header
    assert "Facebook Page Connection" in connection_header
    assert "Enter your Facebook Page details for the n8n workflow." in connection_header
    assert "{% if not connection_is_configured %}" in connection_header
    assert "cf-messenger-page-strip" in connection_header
    assert "cf-messenger-page-summary" in connection_header
    assert "cf-messenger-page-details" in connection_header
    assert "cf-messenger-page-item" in connection_header
    assert "cf-messenger-page-name" in connection_header
    assert "cf-messenger-page-icon" not in connection_header
    assert connection_header.index("Facebook Page Connection") < connection_header.index("cf-messenger-page-strip")
    assert connection_header.index("cf-messenger-page-strip") < connection_header.index("cf-badge-active")
    assert connection_header.index("cf-messenger-page-summary") < connection_header.index("cf-messenger-page-details")
    assert "Facebook Page:" in connection_header
    assert "App ID:" in connection_header
    assert "Page ID:" in connection_header
    assert "cf-badge-active" in connection_header
    assert '<i data-lucide="check-circle-2" class="h-3 w-3" aria-hidden="true"></i> Connected' in connection_header
    assert '<i data-lucide="check-circle-2" class="h-3 w-3" aria-hidden="true"></i> Active' not in connection_header
    assert "cf-status-cancelled" in connection_header
    assert "Page: <code" not in connection_card
    assert ".cf-messenger-page-strip" in css
    assert ".cf-messenger-page-summary" in css
    assert ".cf-messenger-page-details" in css
    assert ".cf-messenger-page-item" in css
    assert ".cf-messenger-page-name" in css
    assert ".cf-messenger-page-icon" not in css
    assert "padding: .45rem .65rem;" in css

    footer_start = connection_card.index("cf-messenger-connection-actions")
    footer = connection_card[footer_start:]
    assert "border-t border-[var(--cf-line)]" in footer
    assert "sm:justify-end" in footer
    assert "Save Settings" in footer
    assert "Disconnect" in footer
    assert "{% else %}" in footer
    assert footer.index("Disconnect") < footer.index("{% else %}") < footer.index("Save Settings")


def test_messenger_secret_reveal_buttons_do_not_overlap_input_border():
    template = source_text("dashboard/templates/dashboard/messenger_settings.html")
    css = css_text()

    reveal_buttons = re.findall(r'<button type="button" class="([^"]+)"[^>]+data-secret-toggle', template)

    assert len(reveal_buttons) == 2
    for button_class in reveal_buttons:
        button_tokens = class_tokens_from_value(button_class)
        assert_class_tokens(
            button_tokens,
            "cf-secret-toggle",
            "top-1/2",
            "-translate-y-1/2",
            "right-1.5",
            "h-10",
            "w-10",
            "justify-center",
            "border-0",
            "bg-transparent",
            "p-0",
        )
        assert "inset-y-0" not in button_tokens
        assert_not_class_token_group(button_tokens, "h-8", "w-8")
    assert ".cf-secret-toggle:focus-visible" in css
    assert "box-shadow: inset 0 0 0 2px var(--cf-focus);" in css


def test_auth_password_visibility_buttons_fit_inside_input_border():
    login = source_text("templates/accounts/login.html")
    signup = source_text("templates/accounts/signup.html")
    password_toggle = css_rule_block(".cf-password-toggle")

    assert "cf-secret-toggle cf-password-toggle" in login
    assert "cf-secret-toggle cf-password-toggle" in signup
    assert "width: 2rem;" in password_toggle
    assert "min-width: 2rem;" in password_toggle
    assert "height: 2rem;" in password_toggle
    assert "min-height: 2rem;" in password_toggle


def test_calendar_page_header_groups_description_actions_and_filters():
    template = source_text("templates/dashboard/calendar.html")

    assert "<div class=\"cf-page-header\">\n    <div>\n      <h1 class=\"cf-page-title ui-page-title\">Calendar</h1>\n      <p class=\"cf-page-description\">Drag-ready appointment calendar with status colors.</p>" in template
    assert "href=\"{% url 'dashboard:appointments' %}\" class=\"cf-btn cf-btn-primary\"" in template
    assert "data-lucide=\"calendar-plus\"" in template
    assert "Add appointment</a>" in template
    assert "id=\"calendar-toolbar\" class=\"cf-toolbar\"" in template
    assert "class=\"cf-calendar-tools\"" not in template

    header_index = template.index("class=\"cf-page-header\"")
    toolbar_index = template.index("id=\"calendar-toolbar\"")
    card_index = template.index("class=\"cf-card cf-calendar-card")
    assert header_index < toolbar_index < card_index


def test_dashboard_shell_uses_task_2_navigation_groups_and_labels():
    template = dashboard_base_text()
    operations_group = re.search(
        r">Operations</p>(?P<body>.*?)(?:<p class=\"[^\"]*uppercase tracking-widest[^\"]*\">|</nav>)",
        template,
        re.DOTALL,
    ).group("body")
    setup_group = re.search(
        r">Setup</p>(?P<body>.*?)(?:<p class=\"[^\"]*uppercase tracking-widest[^\"]*\">|</nav>)",
        template,
        re.DOTALL,
    ).group("body")

    assert ">Operations<" in template
    assert ">Setup<" in template
    assert ">Practice<" not in template
    assert ">Account<" not in template
    assert "label=\"Overview\"" in template
    assert 'label="Services"' in operations_group
    assert "label=\"Assistant\"" in template
    assert 'url_name="dashboard:widget_embed"' in setup_group
    assert 'icon="panel-top-open" label="Booking Widget"' in template
    nav_link_template = source_text("templates/dashboard/partials/nav_link.html")

    assert 'url_name="dashboard:yakap" icon="shield-check" label="YAKAP" hidden=True' in setup_group
    assert 'url_name="dashboard:billing" icon="credit-card" label="Billing" hidden=True' in setup_group
    assert "{% if hidden %}hidden{% endif %}" in nav_link_template
    assert "icon=\"message-circle\" label=\"Assistant\"" in template
    assert '<span class="block max-w-full truncate">Overview</span>' in template
    assert "label=\"Dashboard\"" not in template
    assert '<span class="block max-w-full truncate">Home</span>' not in template
    assert ">Main<" not in template
    assert ">Config<" not in template


def test_dashboard_sidebar_excludes_profile_and_logout_actions():
    template = dashboard_base_text()
    sidebar = re.search(r"<aside\b.*?</aside>", template, re.DOTALL).group(0)
    topbar = re.search(r"<header\b.*?</header>", template, re.DOTALL).group(0)

    assert 'label="Profile"' not in sidebar
    assert "<span>Logout</span>" not in sidebar
    assert "dashboard:profile" in topbar
    assert "accounts:logout" in topbar


def test_billing_page_shows_manual_v1_pricing_and_ai_allowances():
    template = source_text("templates/dashboard/billing.html")

    assert "₱999/mo" in template
    assert "₱2,499/mo" in template
    assert "Free Trial" in template
    assert "250 appointments/month" in template
    assert "1,000 AI messages/month included" in template
    assert "Extra AI message packs available" in template
    assert "AI usage is capped to protect service reliability" in template
    assert "₱1,999/mo" not in template


def test_dashboard_shell_has_accessible_toasts_and_icon_buttons():
    template = dashboard_base_text()

    assert "aria-label=\"Open sidebar\"" in template
    assert "aria-label=\"Close sidebar\"" in template
    assert "aria-label=\"Open account menu\"" in template
    assert "aria-label=\"Dismiss notification\"" in template
    assert "cf-toast-container" in template
    assert "aria-live=\"polite\"" in template
    assert "aria-atomic=\"false\"" in template
    assert "fixed right-4 top-24 z-[70] flex w-full max-w-sm flex-col gap-3" not in template
    assert "z-[70]" not in template
    assert "role=\"alert\"" in template
    assert ":role=\"toast.type === 'error' ? 'alert' : 'status'\"" in template
    assert "role=\"status\"" in template
    assert "cf-toast-close mt-0.5" not in template


def test_dashboard_shell_maps_all_toast_status_types():
    template = dashboard_base_text()

    assert "{% if 'error' in message.tags %}cf-toast-error" in template
    assert "{% elif 'warning' in message.tags %}cf-toast-warning" in template
    assert "{% elif 'info' in message.tags %}cf-toast-info" in template
    assert "{% else %}cf-toast-success" in template
    assert ":class=\"toastClass(toast.type)\"" in template
    assert "toastClass(type)" in template
    assert "cf-toast-error" in template
    assert "cf-toast-success" in template
    assert "cf-toast-warning" in template
    assert "cf-toast-info" in template
    assert "toastIcon(type)" in template
    assert "if (type === 'error') return 'alert-circle';" in template
    assert "if (type === 'warning') return 'alert-triangle';" in template
    assert "if (type === 'info') return 'info';" in template
    assert "return 'check-circle';" in template


def test_dashboard_toasts_render_type_specific_icons():
    template = dashboard_base_text()

    assert "data-lucide=\"alert-circle\"" in template
    assert "data-lucide=\"alert-triangle\"" in template
    assert "data-lucide=\"info\"" in template
    assert "data-lucide=\"check-circle\"" in template
    assert ":data-lucide=\"toastIcon(toast.type)\"" in template
    assert "class=\"cf-toast-icon\"" in template


def test_dashboard_dynamic_toasts_accept_single_or_multiple_htmx_messages():
    template = dashboard_base_text()

    assert "@toast-message.window=\"addToastFromEvent($event.detail)\"" in template
    assert "addToastFromEvent(detail)" in template
    assert "Array.isArray(detail)" in template


def test_dashboard_dynamic_toasts_refresh_lucide_icons_after_insert():
    template = dashboard_base_text()

    assert "refreshIcons()" in template
    assert "this.$nextTick(() => { if (typeof lucide !== 'undefined') lucide.createIcons(); })" in template
    assert "this.refreshIcons();" in template


def test_dashboard_htmx_error_toast_dispatches_to_window():
    template = dashboard_base_text()

    assert "window.dispatchEvent(new CustomEvent('toast-message'" in template
    assert "document.dispatchEvent(new CustomEvent('toast-message'" not in template


def test_dashboard_shell_prevents_hidden_mobile_sidebar_focus():
    template = dashboard_base_text()

    assert "matchMedia('(min-width: 1024px)')" in template
    assert ":inert=\"!sidebarOpen && !isDesktop\"" in template
    assert ":aria-hidden=\"(!sidebarOpen && !isDesktop).toString()\"" in template


def test_dashboard_search_and_account_menu_have_accessible_state():
    template = dashboard_base_text()

    assert "aria-label=\"Search clinic records\"" in template
    assert ":aria-expanded=\"dropdownOpen.toString()\"" in template
    assert "aria-controls=\"account-menu-panel\"" in template
    assert "id=\"account-menu-panel\"" in template
    assert "@keydown.escape.window=\"dropdownOpen = false\"" in template


def test_dashboard_topbar_search_matches_responsive_width_spec():
    template = dashboard_base_text()

    assert "cf-topbar-search min-w-0 flex-1 md:max-w-[420px]" in template
    assert "max-w-[200px]" not in template


def test_dashboard_mobile_topbar_centers_search_between_menu_and_avatar():
    template = dashboard_base_text()

    topbar = re.search(r"<header\b(?P<attrs>[^>]*)>", template, re.DOTALL)
    assert topbar is not None
    assert "gap-3" in topbar.group("attrs")
    assert "md:gap-0" in topbar.group("attrs")

    mobile_search_row = re.search(
        r"<div class=\"(?P<class>[^\"]*flex[^\"]*items-center[^\"]*)\">\s*"
        r"<button @click=\"sidebarOpen = true\"",
        template,
        re.DOTALL,
    )
    assert mobile_search_row is not None
    row_class = mobile_search_row.group("class")
    assert "min-w-0" in row_class
    assert "gap-3" in row_class
    assert "md:gap-2" in row_class


def test_dashboard_dynamic_toasts_remove_by_stable_id():
    template = dashboard_base_text()

    assert "toastId" in template
    assert ":key=\"toast.id\"" in template
    assert "removeToast(toast.id)" in template
    assert "toasts.shift()" not in template
    assert "toasts.splice(index, 1)" not in template


def test_dashboard_htmx_loading_state_preserves_accessible_name():
    template = dashboard_base_text()

    assert "btn.dataset.originalAriaLabel" in template
    assert "aria-busy" in template
    assert "aria-disabled" in template
    assert "sr-only" in template
    assert "pointer-events-none" in template
    assert "btn.tagName === 'BUTTON'" in template
    assert "btn.innerHTML = '<i data-lucide=\"loader-2\"" not in template


def test_dashboard_htmx_focus_uses_temporary_target_without_disabling_controls():
    template = dashboard_base_text()

    assert "data-cf-temp-focus" in template
    assert "removeAttribute('tabindex')" in template
    assert "addEventListener('blur'" in template
    assert "querySelector('h2, h3, button, a, input, [tabindex]')" not in template


def test_search_results_use_design_system_search_classes():
    template = search_results_text()

    assert "cf-search-result" in template
    assert "cf-muted" in template
    assert "text-slate-" not in template
    assert "hover:bg-cyan" not in template


def test_search_results_make_service_rows_keyboard_accessible():
    template = search_results_text()

    assert "href=\"{% url 'dashboard:services' %}#service-card-{{ service.id }}\"" in template
    assert "<a href=\"{% url 'dashboard:services' %}#service-card-{{ service.id }}\" class=\"cf-search-result" in template
    assert "<div class=\"cf-search-result flex items-center gap-3 px-4 py-2.5 text-sm\">\n          <i data-lucide=\"stethoscope\"" not in template


def test_task_3_table_partials_use_shared_table_surface():
    for name in [
        "appointment_list.html",
        "patient_list.html",
        "patient_detail_content.html",
    ]:
        template = partial_text(name)
        assert "cf-table-wrap" in template
        assert "cf-table-header" in template
        assert "cf-section-title" in template
        assert "cf-muted" in template
        assert "cf-table-scroll" in template
        assert "cf-table" in template


def test_dashboard_tables_use_bounded_mobile_scroll_regions():
    for relative_path in [
        "templates/dashboard/home.html",
        "templates/dashboard/settings.html",
        "templates/dashboard/business_hours.html",
        "templates/dashboard/unavailable_dates.html",
        "templates/dashboard/partials/appointment_list.html",
        "templates/dashboard/partials/patient_list.html",
        "templates/dashboard/partials/patient_detail_content.html",
    ]:
        template = source_text(relative_path)
        table_count = template.count('<table class="cf-table')
        scroll_regions = re.finditer(
            r'<div class="cf-table-scroll"(?P<attrs>[^>]*)>(?P<body>.*?)(?=<div class="cf-table-scroll"|$)',
            template,
            re.DOTALL,
        )

        assert table_count > 0
        covered_table_count = 0
        for region in scroll_regions:
            attrs = region.group("attrs")
            table_count_in_region = region.group("body").count('<table class="cf-table')
            label = re.search(r'aria-label="([^"]+)"', attrs)

            assert 'tabindex="0"' in attrs
            assert label is not None
            assert label.group(1).strip()
            assert table_count_in_region == 1
            covered_table_count += table_count_in_region
        assert covered_table_count == table_count


def test_responsive_table_css_uses_inner_scroll_and_mobile_width_variants():
    css = css_text()
    page = css_rule_block(".cf-page")
    page_children = css_rule_block(".cf-page > *")
    wrap = css_rule_block(".cf-table-wrap")
    scroll = css_rule_block(".cf-table-scroll")
    table = css_rule_block(".cf-table")
    mobile = re.search(r"@media \(max-width: 640px\) \{(?P<body>.*?)^\}", css, re.DOTALL | re.MULTILINE).group("body")

    assert "min-width: 0;" in page
    assert "min-width: 0;" in page_children
    assert "overflow: hidden;" in wrap
    assert "width: 100%;" in scroll
    assert "max-width: 100%;" in scroll
    assert "min-width: 0;" in scroll
    assert "overflow-x: auto;" in scroll
    assert "-webkit-overflow-scrolling: touch;" in scroll
    assert "overscroll-behavior-inline: contain;" in scroll
    assert "contain: layout paint;" in scroll
    assert "min-width: max(100%, 44rem);" in table
    assert "cf-table-compact" in css
    assert "cf-table-form" in css
    assert "cf-table-wide" in css
    assert ".cf-table { min-width: max(100%, 36rem); }" in mobile
    assert ".cf-table-compact { min-width: max(100%, 32rem); }" in mobile
    assert ".cf-table-form { min-width: max(100%, 42rem); }" in mobile
    assert ".cf-table-wide { min-width: max(100%, 48rem); }" in mobile


def test_patient_empty_search_keeps_table_heading_and_columns_visible():
    template = partial_text("patient_list.html")

    assert "{% empty %}" in template
    assert '<td colspan="6">' in template
    assert template.index("cf-table-header") < template.index("<thead")
    assert template.index("<thead") < template.index("{% empty %}")
    assert template.index("{% empty %}") < template.index("No patients found")
    assert "cf-card cf-empty-state" not in template


def test_services_empty_states_use_table_surface_without_visible_table_headers():
    template = partial_text("service_list.html")
    empty_content_class = 'class="flex flex-col items-center justify-center px-6 py-14 text-center"'

    assert template.count('class="col-span-full cf-table-wrap"') == 2
    assert template.count('class="cf-table-scroll"') == 2
    assert template.count('<table class="cf-table cf-table-wide">') == 2
    assert template.count('<td colspan="5">') == 2
    assert template.count(empty_content_class) == 2
    assert template.index("cf-table-wrap") < template.index("No active services")
    assert template.rindex("cf-table-wrap") < template.index("No archived services")
    assert "cf-table-header" not in template
    assert "<thead" not in template
    assert ">Active services<" not in template
    assert ">Archived services<" not in template
    assert "cf-services-empty-state" not in template
    assert "cf-card cf-empty-state" not in template
    assert ".cf-services-empty-state" not in css_text()


def test_task_3_modal_partials_use_accessible_modal_anatomy():
    for name in ["add_patient_modal.html", "patient_detail.html", "faq_row.html"]:
        template = partial_text(name)
        assert "cf-modal-backdrop" in template
        assert "cf-modal" in template
        assert "cf-modal-header" in template
        assert "cf-modal-body" in template
        assert "cf-modal-footer" in template
        assert "role=\"dialog\"" in template
        assert "aria-modal=\"true\"" in template
        assert "aria-labelledby=" in template


def test_dashboard_modal_shells_use_canonical_spacing_and_accessibility():
    modal_templates = [
        "templates/dashboard/appointments.html",
        "templates/dashboard/calendar.html",
        "templates/dashboard/patients.html",
        "templates/dashboard/services.html",
    ]

    for path in modal_templates:
        template = source_text(path)
        assert "cf-modal max-w-" not in template
        assert not re.search(r'class="[^"]*cf-modal[^"]*\bp-6\b', template)
        assert not re.search(r'id="(?:detail|edit|add)-modal-body" class="p-6"', template)
        assert "role=\"dialog\"" in template
        assert "aria-modal=\"true\"" in template
        assert "aria-labelledby=" in template


def test_modal_form_partials_own_body_and_footer_spacing():
    for name in ["appointment_form.html", "patient_edit_modal_form.html", "service_form.html"]:
        template = partial_text(name)
        assert "cf-modal-header" in template
        assert "cf-modal-body" in template
        assert "cf-modal-footer" in template


def test_unavailable_date_modals_use_icon_button_close_controls():
    for path in ["templates/dashboard/settings.html", "templates/dashboard/unavailable_dates.html"]:
        template = source_text(path)
        assert "rounded-2xl p-2 text-[var(--cf-muted)]" not in template
        assert ">×</button>" not in template
        assert "cf-icon-btn" in template


def test_task_3_shared_partials_avoid_legacy_cyan_slate_field_utilities():
    legacy_patterns = legacy_utility_patterns(include_font_weight=True)
    for name in [
        "appointment_detail.html",
        "appointment_form.html",
        "add_patient_modal.html",
        "duplicate_list.html",
        "faq_row.html",
        "merge_confirm.html",
        "merge_success.html",
        "patient_edit_modal_form.html",
        "patient_row.html",
        "service_form.html",
        "service_row.html",
    ]:
        template = partial_text(name)
        for pattern in legacy_patterns:
            assert pattern not in template
        assert "cf-error" in template or name not in [
            "appointment_detail.html",
            "appointment_form.html",
            "add_patient_modal.html",
            "faq_row.html",
            "patient_edit_modal_form.html",
            "service_form.html",
        ]


def test_potential_duplicates_header_buttons_reference_edit_appointment_styles_at_smaller_size():
    template = partial_text("duplicate_list.html")
    button_classes = {}
    button_bodies = {}
    for match in CF_BTN_TAG_RE.finditer(template):
        label = visible_button_text(match.group("body"))
        if label in {"Refresh", "Close"}:
            button_classes[label] = re.search(r'class="([^"]*)"', match.group("attrs")).group(1)
            button_bodies[label] = match.group("body")

    assert set(button_classes) == {"Refresh", "Close"}
    assert "cf-btn-primary" in button_classes["Refresh"]
    assert "cf-btn-secondary" not in button_classes["Refresh"]
    assert "cf-btn-secondary" in button_classes["Close"]
    assert "cf-btn-muted" not in button_classes["Close"]
    assert "cf-btn-ghost" not in button_classes["Close"]
    for button_class in button_classes.values():
        assert "cf-btn" in button_class
        assert "cf-btn-sm" in button_class
        assert "flex-1" not in button_class

    assert 'data-lucide="refresh-cw"' in button_bodies["Refresh"]
    assert 'data-lucide="loader-2"' in button_bodies["Refresh"]
    assert 'data-lucide="x-circle"' in button_bodies["Close"]


def test_service_row_toggle_button_uses_stateful_action_styles():
    template = partial_text("service_row.html")
    muted_button = css_rule_block(".cf-btn-muted")
    activate_button = css_rule_block(".cf-service-activate-action")
    activate_hover = css_rule_block(".cf-service-activate-action:hover")
    edit_hover = css_rule_block(".cf-service-edit-action:hover")
    archive_hover = css_rule_block(".cf-service-archive-action:hover")

    assert 'class="cf-btn cf-btn-xs cf-btn-secondary cf-service-edit-action"' in template
    assert 'class="cf-btn cf-btn-xs cf-btn-muted cf-service-archive-action"' in template
    assert "cf-btn cf-btn-xs {% if service.is_active %}cf-btn-danger{% else %}cf-service-activate-action{% endif %}" in template
    assert "{% if service.is_active %}cf-btn-danger{% else %}cf-btn-primary{% endif %}" not in template
    assert '{{ service.is_active|yesno:"Deactivate,Activate" }}' in template
    assert "border-color:" in muted_button
    assert "background: var(--cf-surface);" in muted_button
    assert "var(--cf-brand)" not in muted_button
    assert "var(--cf-danger)" not in muted_button
    assert "border-color:" in activate_button
    assert "background: var(--cf-surface);" in activate_button
    assert "color: var(--cf-lemon);" in activate_button
    assert "var(--cf-brand)" not in activate_button
    assert "background: var(--cf-lemon);" in activate_hover
    assert "border-color: var(--cf-lemon);" in activate_hover
    assert "color: #fff;" in activate_hover
    assert "background: var(--cf-brand);" in edit_hover
    assert "border-color: var(--cf-brand);" in edit_hover
    assert "color: #fff;" in edit_hover
    assert "background: var(--cf-ink-secondary);" in archive_hover
    assert "border-color: var(--cf-ink-secondary);" in archive_hover
    assert "color: #fff;" in archive_hover


def test_archived_service_row_has_guarded_delete_confirmation():
    template = partial_text("service_row.html")

    archived_start = template.index("dashboard:restore_service")
    archived_block = template[archived_start:]

    assert "dashboard:delete_service" in archived_block
    assert "Delete service" in archived_block
    assert re.search(r">\s*Delete\s*</button>", archived_block)
    assert not re.search(r"cf-btn cf-btn-xs cf-btn-danger[^>]*>.*?Delete service\s*</button>", archived_block, re.DOTALL)
    assert "This permanently deletes the service only if it has no appointment history." in archived_block
    assert "cf-btn cf-btn-xs cf-btn-danger" in archived_block
    assert "csrf_token" in archived_block
    assert "hx-post=\"{% url 'dashboard:delete_service' service.id %}\"" in archived_block
    assert "hx-target=\"#services-list-container\"" in archived_block
    assert "hx-swap=\"innerHTML\"" in archived_block
    assert "@keydown.tab=\"trapModalFocus($event, $el)\"" in archived_block
    assert "tabindex=\"-1\"" in archived_block
    assert "x-effect=\"if (deleting) focusModal($el)\"" in archived_block
    assert "focusModal(root)" in template
    assert "trapModalFocus(event, root)" in template
    assert "href=\"{% url 'dashboard:delete_service'" not in template


def test_task_3_partial_forms_render_design_system_fields():
    appointment_detail = partial_text("appointment_detail.html")
    add_patient_modal = partial_text("add_patient_modal.html")

    assert "patient_form.as_p" not in add_patient_modal
    assert "{% for field in patient_form %}" in add_patient_modal
    assert "{{ status_form.status }}" in appointment_detail
    assert "{{ status_form.payment_state }}" in appointment_detail
    assert "{{ note_form.body }}" in appointment_detail
    assert "for=\"{{ status_form.status.id_for_label }}\"" in appointment_detail
    assert "for=\"{{ note_form.body.id_for_label }}\"" in appointment_detail


def test_appointment_detail_secondary_metadata_uses_muted_panels():
    appointment_detail = partial_text("appointment_detail.html")
    required_panel_classes = [
        "rounded-[var(--cf-radius)]",
        "bg-[var(--cf-surface-muted)]",
        "p-4",
    ]

    for label in ["Status", "Payment", "Source", "Reference", "Reason / Notes"]:
        block = div_block_containing(appointment_detail, f'<p class="cf-label mb-1">{label}</p>')
        for class_name in required_panel_classes:
            assert class_name in block


def test_appointment_detail_has_separate_delete_mode():
    template = partial_text("appointment_detail.html")

    assert "Delete appointment" in template
    assert "Delete permanently" in template
    assert "dashboard:delete_appointment" in template
    assert "mode === 'delete'" in template
    assert "modal_source" in template
    assert "hx-include=\"#filter-form\"" in template
    assert "cf-btn cf-btn-danger" in template
    assert "href=\"{% url 'dashboard:delete_appointment'" not in template


def test_appointment_delete_success_closes_open_detail_modals():
    appointments = source_text("templates/dashboard/appointments.html")
    patient_detail = partial_text("patient_detail.html")

    assert 'x-on:appointment-deleted.camel' in appointments
    assert 'detailOpen=false' in appointments
    assert 'appointments-table' in appointments
    assert '.focus()' in appointments
    assert '<div id="appointments-table" tabindex="-1">' in appointments
    assert '<div id="detail-modal-body">\n        <div class="cf-modal-header sr-only">\n          <h2 id="appointment-detail-title"' in appointments
    assert 'x-on:appointment-deleted.camel' in patient_detail
    assert 'detailOpen=false' in patient_detail
    assert 'visit-history-heading' in patient_detail
    assert '.focus()' in patient_detail


def test_patient_visit_history_marks_appointment_detail_source():
    template = partial_text("patient_detail_content.html")

    assert "dashboard:appointment_detail' appointment.id %}?source=patient" in template
    assert 'id="visit-history-heading"' in template
    assert 'tabindex="-1"' in template


def test_patient_rows_have_guarded_delete_confirmation():
    patient_list = partial_text("patient_list.html")
    patient_row = partial_text("patient_row.html")
    table_scroll = div_block_containing(patient_list, 'class="cf-table-scroll"')

    for template in [patient_list, patient_row]:
        assert "cf-btn cf-btn-xs cf-btn-danger" in template
        assert re.search(r">\s*Delete\s*</button>", template)
        assert not re.search(r">\s*Delete patient\s*</button>", template)
        assert "href=\"{% url 'dashboard:delete_patient'" not in template

    assert "dashboard:delete_patient" in patient_list
    assert "Delete patient" in patient_list
    assert "Patients with appointment history cannot be deleted." in patient_list
    assert "deletingPatientId:null" in patient_list
    assert "deletingPatientId = '{{ patient.id }}'" in patient_list
    assert "x-show=\"deletingPatientId === '{{ patient.id }}'\"" in patient_list
    assert "x-on:patient-delete-blocked.window=\"deletingPatientId=null\"" in patient_list
    assert "cf-modal-backdrop" not in table_scroll
    assert "cf-modal-backdrop" not in patient_row

    assert "dashboard:delete_patient" not in patient_row
    assert "Patients with appointment history cannot be deleted." not in patient_row

    for template in [patient_list]:
        assert "hx-target=\"#patient-list\"" in template
        assert "hx-include=\"#patient-toolbar\"" in template
        assert "@keydown.tab=\"trapModalFocus($event, $el)\"" in template
        assert "x-effect=\"if (deletingPatientId === '{{ patient.id }}') focusModal($el)\"" in template
        assert "tabindex=\"-1\"" in template
        assert "csrf_token" in template
        assert "cf-modal-header flex items-center justify-between" in template
        assert "cf-icon-box h-10 w-10 bg-[var(--cf-status-cancelled-bg)] text-[var(--cf-red)]" in template
        assert "aria-label=\"Close delete patient modal\"" in template
        assert "cf-modal-footer" in template
        assert "class=\"inline\"" in template
        assert "data-lucide=\"x-circle\"" in template


def test_patient_detail_has_guarded_delete_confirmation():
    detail = partial_text("patient_detail.html")
    content = partial_text("patient_detail_content.html")

    assert "patientDeleteOpen:false" in detail
    assert "patientDeleteOpen=false" in detail
    assert "x-on:patient-delete-blocked.window=\"patientDeleteOpen=false\"" in detail
    assert "focusModal(root)" in detail
    assert "dashboard:delete_patient" in detail
    assert "Delete patient" in detail
    assert re.search(r">\s*Delete\s*</button>", content)
    assert re.search(r">\s*Delete\s*</button>", detail)
    assert not re.search(r">\s*Delete patient\s*</button>", content)
    assert not re.search(r">\s*Delete patient\s*</button>", detail)
    assert "Patients with appointment history cannot be deleted." in detail
    assert "cf-btn cf-btn-danger" in content
    assert "cf-modal-backdrop" not in content
    assert "@keydown.tab=\"trapModalFocus($event, $el)\"" in detail
    assert "x-effect=\"if (patientDeleteOpen) focusModal($el)\"" in detail
    assert "csrf_token" in detail
    assert "cf-modal-header flex items-center justify-between" in detail
    assert "cf-icon-box h-10 w-10 bg-[var(--cf-status-cancelled-bg)] text-[var(--cf-red)]" in detail
    assert "aria-label=\"Close delete patient modal\"" in detail
    assert "cf-modal-footer" in detail
    assert "class=\"inline\"" in detail
    assert "data-lucide=\"x-circle\"" in detail


def test_patient_detail_uses_defined_radius_tokens_and_semantic_kpi_icons():
    template = partial_text("patient_detail_content.html")

    assert "--cf-rounded" not in template
    assert "rounded-[var(--cf-radius-md)]" in template

    completed_block = div_block_containing(template, '<span class="cf-kpi-label">Completed</span>')
    cancelled_block = div_block_containing(template, '<span class="cf-kpi-label">Cancelled</span>')

    assert "bg-[var(--cf-status-completed-bg)]" in completed_block
    assert "text-[var(--cf-status-completed-text)]" in completed_block
    assert "bg-[var(--cf-status-cancelled-bg)]" in cancelled_block
    assert "text-[var(--cf-status-cancelled-text)]" in cancelled_block


def test_patient_detail_modals_match_dashboard_focus_management():
    detail = partial_text("patient_detail.html")
    content = partial_text("patient_detail_content.html")
    combined = detail + content

    assert "trapModalFocus(event, root)" in detail
    assert "patientDeleteOpen:false" in detail
    assert "detailOpen=false" in detail
    assert "editOpen=false" in detail
    assert "patientDeleteOpen=false" in detail
    assert 'aria-labelledby="appointment-detail-title"' in detail
    assert 'id="appointment-detail-title"' in detail
    assert combined.count('@keydown.tab="trapModalFocus($event, $el)"') == 3
    assert combined.count('tabindex="-1"') >= 3
    assert 'x-effect="if (detailOpen)' in detail
    assert 'x-effect="if (editOpen)' in detail
    assert 'x-effect="if (patientDeleteOpen)' in detail
    assert 'aria-labelledby="patient-delete-modal-title"' in detail
    assert 'cf-modal-backdrop' not in content


def test_patient_detail_visit_history_uses_table_surface_without_nested_card():
    template = partial_text("patient_detail_content.html")
    visit_history = tag_block_containing(template, "section", 'id="visit-history-heading"')
    visit_history_header = opening_tag_containing(visit_history, "div", "sm:justify-between")
    table_wrap = opening_tag_containing(visit_history, "div", "cf-table-wrap")

    assert_class_tokens(class_tokens_from_markup(visit_history), "grid", "gap-4")
    visit_history_header_tokens = class_tokens_from_markup(visit_history_header)
    assert_class_tokens(
        visit_history_header_tokens,
        "flex",
        "flex-col",
        "items-start",
        "gap-3",
        "sm:flex-row",
        "sm:items-center",
        "sm:justify-between",
    )
    assert_not_class_token_group(visit_history_header_tokens, "flex", "items-center", "justify-between")
    assert '<h2 id="visit-history-heading" tabindex="-1" class="cf-section-title">Visit History</h2>' in visit_history
    assert_class_tokens(class_tokens_from_markup(table_wrap), "cf-table-wrap")
    for div_opening in re.findall(r"<div\b[^>]*>", visit_history):
        if 'class="' not in div_opening:
            continue
        assert_not_class_token_group(class_tokens_from_markup(div_opening), "cf-card", "p-5", "lg:p-6")


def test_patient_detail_visit_history_summary_matches_faq_summary_pattern():
    template = partial_text("patient_detail_content.html")
    summary = div_block_containing(template, "visit-history-summary")

    assert 'id="visit-history-summary"' in summary
    assert 'class="cf-faq-summary"' in summary
    assert 'aria-label="Visit history summary"' in summary
    assert '<span class="cf-faq-summary-metric">{{ kpi_total }} total</span>' in summary
    assert 'cf-faq-summary-separator' in summary
    assert '<span class="cf-faq-summary-metric">Last: {{ last_appointment.starts_at|date:"M j, Y" }}</span>' in summary
    assert "&middot; Last:" not in summary


def test_patient_detail_notes_and_empty_state_use_canonical_tokens():
    template = partial_text("patient_detail_content.html")
    notes_block = div_block_containing(template, "No notes added yet.")

    assert "rounded-[var(--cf-radius)]" in notes_block
    assert "bg-[var(--cf-surface-muted)]" in notes_block
    assert "rounded-lg" not in notes_block
    assert "cf-card cf-empty-state" in template
    assert "text-sm font-semibold" in template
    assert "text-xl font-bold" not in template


def test_task_3_form_widgets_use_design_system_classes():
    expected = {
        "appointments/forms.py": [
            '_INPUT = "cf-input"',
            '_SELECT = "cf-select"',
            '_TEXTAREA = "cf-textarea"',
        ],
        "patients/forms.py": [
            '_INPUT = "cf-input"',
            '_SELECT = "cf-select"',
            '_TEXTAREA = "cf-textarea"',
        ],
        "services/forms.py": [
            '_INPUT = "cf-input"',
            '_SELECT = "cf-select"',
            '_TEXTAREA = "cf-textarea"',
            '_CHECKBOX = "cf-checkbox"',
        ],
    }
    legacy_patterns = [
        f"border-{'slate'}",
        f"text-{'slate'}",
        f"focus:border-{'cyan'}",
        f"focus:ring-{'cyan'}",
        f"text-{'cyan'}",
    ]

    for relative_path, snippets in expected.items():
        source = source_text(relative_path)
        for snippet in snippets:
            assert snippet in source
        for pattern in legacy_patterns:
            assert pattern not in source


def test_faq_section_uses_split_composer_layout():
    template = source_text("templates/dashboard/assistant_settings.html")
    summary = div_block_containing(template, "faq_total_count")
    composer = div_block_containing(template, "faq_form.is_active")

    assert "cf-faq-shell" in template
    assert "cf-faq-header" in template
    assert "cf-faq-layout" in template
    assert "cf-faq-composer" in template
    assert "cf-faq-list" in template
    assert "cf-faq-summary" in template
    assert "{{ faq_total_count }}" in template
    assert "{{ faq_visible_count }}" in template
    assert "Patient-facing assistant copy" in template
    assert summary.count("cf-faq-summary-metric") == 2
    assert summary.count("cf-faq-summary-separator") == 1
    assert "{{ faq_total_count }} total" in summary
    assert "{{ faq_visible_count }} visible" in summary
    assert summary.index("{{ faq_total_count }} total") < summary.index("cf-faq-summary-separator")
    assert summary.index("cf-faq-summary-separator") < summary.index("{{ faq_visible_count }} visible")
    assert "cf-faq-summary-pill" not in summary
    assert "Visible to patients" in composer
    assert "Make this FAQ visible" not in composer


def test_assistant_page_messenger_mode_waits_for_save_button():
    template = source_text("templates/dashboard/assistant_settings.html")

    assert "Messenger Response Mode" in template
    assert "role=\"radiogroup\"" in template
    assert "name=\"{{ ai_form.messenger_response_mode.html_name }}\"" in template
    assert "value=\"quick_replies\"" in template
    assert "value=\"ai\"" in template
    messenger_mode = template[
        template.index("Messenger Response Mode") : template.index("Communication Tone")
    ]
    assert "requestSubmit" not in messenger_mode
    assert "onchange=" not in messenger_mode
    assert "Save Assistant Settings" in template
    assert "No AI tokens are consumed" in template
    assert "No quick-reply buttons are shown" in template
    assert "Messenger AI mode is independent from the website Assistant switch" in template
    assert "AI mode only takes over when AI replies are enabled" not in template


def test_assistant_page_messenger_mode_uses_custom_aqua_radio_cards():
    template = source_text("templates/dashboard/assistant_settings.html")

    assert template.count('class="cf-choice-card"') == 2
    assert template.count('class="cf-choice-card-input"') == 2
    assert template.count('class="cf-choice-card-mark"') == 2

    choice_card = css_rule_block(".cf-choice-card")
    selected_card = css_rule_block(".cf-choice-card:has(.cf-choice-card-input:checked)")
    mark = css_rule_block(".cf-choice-card-mark")
    selected_mark = css_rule_block(".cf-choice-card:has(.cf-choice-card-input:checked) .cf-choice-card-mark::after")

    assert "border: 1px solid var(--cf-line);" in choice_card
    assert "border-color: var(--cf-brand);" in selected_card
    assert "background: linear-gradient(180deg, var(--cf-surface) 0%, var(--cf-brand-soft) 100%);" in selected_card
    assert "border-radius: var(--cf-radius-pill);" in mark
    assert "background: var(--cf-brand);" in selected_mark
    assert "transform: scale(1);" in selected_mark


def test_voice_agent_page_uses_dashboard_design_system_patterns():
    template = source_text("templates/dashboard/voice_agent.html")
    tabs = tag_block_containing(template, "div", 'class="cf-tabs"')
    channel_controls = tag_block_containing(template, "div", 'data-section="voice-agent-channel-controls"')
    mic_source = tag_block_containing(template, "div", 'data-section="voice-agent-mic-source"')
    transcript_panel = tag_block_containing(template, "div", 'aria-label="Voice test conversation transcript"')
    switch_row = css_rule_block(".cf-switch-row")
    switch_track = css_rule_block(".cf-switch-track")
    switch_thumb = css_rule_block(".cf-switch-thumb")
    switch_checked_track = css_rule_block(".cf-switch-row:has(.cf-switch-input:checked) .cf-switch-track")
    switch_checked_thumb = css_rule_block(".cf-switch-row:has(.cf-switch-input:checked) .cf-switch-thumb")
    tab_buttons = re.findall(r"<button\b[^>]*>", tabs)
    switch_labels = re.findall(r"<label\b[^>]*>", channel_controls)
    switch_inputs = re.findall(r"<input\b[^>]*>", channel_controls)
    switch_spans = re.findall(r"<span\b[^>]*\bclass=\"[^\"]*\"[^>]*>", channel_controls)

    assert len(tab_buttons) == 2
    for tab_button in tab_buttons:
        assert_class_tokens(class_tokens_from_markup(tab_button), "cf-tab")
    assert "tab==='configure' ? 'cf-tab-active' : ''" in template
    assert "tab==='test' ? 'cf-tab-active' : ''" in template
    assert "inline-flex rounded-2xl" not in template
    assert "role=\"tab\"" not in tabs

    assert sum("cf-switch-row" in class_tokens_from_markup(label) for label in switch_labels) == 2
    assert sum("cf-switch-input" in class_tokens_from_markup(input_tag) for input_tag in switch_inputs) == 2
    assert "cf-choice-card" not in channel_controls
    assert "cf-choice-card-input" not in channel_controls
    assert "cf-choice-card-mark" not in channel_controls
    assert sum("cf-switch-state" in class_tokens_from_markup(span) for span in switch_spans) == 2
    assert sum("cf-switch-state-on" in class_tokens_from_markup(span) for span in switch_spans) == 2
    assert sum("cf-switch-state-off" in class_tokens_from_markup(span) for span in switch_spans) == 2
    assert sum("cf-switch-track" in class_tokens_from_markup(span) for span in switch_spans) == 2
    assert sum("cf-switch-thumb" in class_tokens_from_markup(span) for span in switch_spans) == 2
    assert ">On<" in channel_controls
    assert ">Off<" in channel_controls
    assert 'name="{{ voice_form.is_enabled.html_name }}"' in channel_controls
    assert 'name="{{ voice_form.is_test_mode_enabled.html_name }}"' in channel_controls
    assert "{{ voice_form.is_enabled.label }}" in channel_controls
    assert "{{ voice_form.is_test_mode_enabled.label }}" in channel_controls
    assert "align-items: center;" in switch_row
    assert "justify-content: space-between;" in switch_row
    assert "border-radius: var(--cf-radius-pill);" in switch_track
    assert "background: var(--cf-status-no-show-bg);" in switch_track
    assert "background: var(--cf-surface);" in switch_thumb
    assert "background: var(--cf-brand);" in switch_checked_track
    assert "transform: translateX(1.5rem);" in switch_checked_thumb

    assert "cf-table-wrap" in template
    assert "cf-table-header" in template
    assert 'class="cf-table cf-table-compact"' in template
    assert "cf-empty-state" in transcript_panel
    assert "No conversation yet" in transcript_panel

    assert "Microphone source" in mic_source
    assert 'id="voice-mic-source"' in mic_source
    assert 'class="cf-select"' in mic_source
    assert 'x-model="selectedMicDeviceId"' in mic_source
    assert 'value="default"' in mic_source
    assert "Default microphone" in mic_source
    assert "x-for=\"device in micDevices\"" in mic_source
    assert "x-text=\"micSourceHelp\"" in mic_source
    assert "loadMicrophones({ requestPermission: true })" in mic_source
    assert "selectedMicDeviceId" in template
    assert "micDevices" in template
    assert "micSourceHelp" in template
    assert "loadMicrophones" in template
    assert "activateSelectedMicrophone" in template
    assert "navigator.mediaDevices" in template
    assert "enumerateDevices" in template
    assert "getUserMedia" in template


def test_assistant_ai_provider_card_uses_compact_design_system_layout():
    template = source_text("templates/dashboard/assistant_settings.html")
    forms = source_text("clinics/forms.py")
    data_index = template.index('data-section="ai-provider-settings"')
    section_start = template.rindex("<section", 0, data_index)
    section_end = template.index("\n  <section", section_start + 1)
    provider_section = template[section_start:section_end]
    form_start = forms.index("class AIProviderSettingsForm")
    form_end = forms.index("class ClinicFAQForm", form_start)
    provider_form = forms[form_start:form_end]

    assert '<section class="cf-card p-6" data-section="ai-provider-settings"' in provider_section
    assert "cf-card overflow-hidden p-0" not in provider_section
    assert "border-b border-[var(--cf-line)]" not in provider_section
    assert "cf-card border border-[var(--cf-line)] bg-[var(--cf-surface-muted)] p-4 shadow-none" in provider_section
    assert "data-ai-provider-column=" not in provider_section
    assert "data-ai-provider-row=" not in provider_section
    assert 'data-ai-provider-layout="responsive-grid" class="grid gap-4 lg:grid-cols-2"' in provider_section
    assert 'data-ai-provider-field="provider" class="cf-field order-1 lg:order-1"' in provider_section
    assert 'data-ai-provider-field="base-url" class="cf-field order-2 lg:order-3"' in provider_section
    assert 'data-ai-provider-field="api-key" class="cf-field order-3 lg:order-5"' in provider_section
    assert 'data-ai-provider-field="primary-model" class="cf-field order-4 lg:order-2"' in provider_section
    assert 'data-ai-provider-field="fallback-model" class="cf-field order-5 lg:order-4"' in provider_section
    assert provider_section.index('data-ai-provider-field="provider"') < provider_section.index('data-ai-provider-field="base-url"')
    assert provider_section.index('data-ai-provider-field="base-url"') < provider_section.index('data-ai-provider-field="api-key"')
    assert provider_section.index('data-ai-provider-field="api-key"') < provider_section.index('data-ai-provider-field="primary-model"')
    assert provider_section.index('data-ai-provider-field="primary-model"') < provider_section.index('data-ai-provider-field="fallback-model"')
    assert "Choose the AI endpoint for this clinic." in provider_section
    assert "Primary model used first for the selected provider." in provider_section
    assert "Required only for OpenAI-compatible providers." in provider_section
    assert "Fallback model retries only if the primary model fails" in provider_section
    assert "{{ ai_provider_form.api_key }}" in provider_section
    assert provider_section.count('class="cf-field ') >= 5
    assert 'widget=forms.URLInput(attrs={"class": _INPUT' in provider_form
    assert provider_form.count('widget=forms.Select(attrs={"class": _SELECT})') >= 2
    assert '"provider": forms.Select(attrs={"class": _SELECT})' in provider_form
    assert 'SavedProviderSecretInput(attrs={"class": f"{_INPUT} pr-12"' in provider_form
    assert '"is_enabled"' not in provider_form
    assert 'name="is_enabled"' not in provider_section


def test_faq_summary_metrics_use_aqua_soft_pills():
    metric_block = css_rule_block(".cf-faq-summary-metric")
    separator_block = css_rule_block(".cf-faq-summary-separator")

    assert "background: var(--cf-brand-soft);" in metric_block
    assert "color: var(--cf-brand-strong);" in metric_block
    assert "border-radius: var(--cf-radius-pill);" in metric_block
    assert "font-variant-numeric: tabular-nums;" in metric_block
    assert "background: var(--cf-input-line);" in separator_block


def faq_action_button(template, aria_label):
    match = re.search(
        rf"<button\b(?P<attrs>[^>]*\baria-label=\"{re.escape(aria_label)}\"[^>]*)>"
        r"(?P<body>.*?)</button>",
        template,
        re.DOTALL,
    )
    assert match is not None
    return match.group("attrs"), match.group("body")


def test_faq_row_controls_are_accessible_icon_actions():
    template = partial_text("faq_row.html")
    edit_attrs, edit_body = faq_action_button(template, "Edit FAQ")
    delete_attrs, delete_body = faq_action_button(template, "Delete FAQ")

    assert "for=\"faq-question-{{ faq.id }}\"" in template
    assert "id=\"faq-question-{{ faq.id }}\"" in template
    assert "for=\"faq-answer-{{ faq.id }}\"" in template
    assert "id=\"faq-answer-{{ faq.id }}\"" in template
    assert "aria-label=\"{% if faq.is_active %}Hide FAQ from patients{% else %}Show FAQ to patients{% endif %}\"" in template
    assert "title=\"Edit FAQ\"" in edit_attrs
    assert "cf-faq-icon-action" in edit_attrs
    assert "data-lucide=\"pencil\"" in edit_body
    assert visible_button_text(edit_body) == ""
    assert "title=\"Delete FAQ\"" in delete_attrs
    assert "cf-faq-icon-action" in delete_attrs
    assert "data-lucide=\"trash-2\"" in delete_body
    assert visible_button_text(delete_body) == ""
    assert "{% if faq.is_active %}Visible{% else %}Hidden{% endif %}" in template


def test_faq_icon_actions_use_accessible_compact_size():
    stylesheet = css_text()
    template = partial_text("faq_row.html")
    edit_attrs, _ = faq_action_button(template, "Edit FAQ")
    delete_attrs, _ = faq_action_button(template, "Delete FAQ")
    action_block = css_rule_block(".cf-faq-icon-action")
    icon_block = css_rule_block(".cf-faq-icon-action svg")
    delete_hover_block = css_rule_block(".cf-faq-delete-action:hover")

    assert "cf-faq-icon-actions" in template
    assert "cf-faq-icon-action" in edit_attrs
    assert "cf-faq-icon-action" in delete_attrs
    assert "cf-faq-delete-action" in delete_attrs
    assert "width: 2rem;" in action_block
    assert "height: 2rem;" in action_block
    assert "border-radius: var(--cf-radius-pill);" in action_block
    assert "width: .95rem;" in icon_block
    assert "height: .95rem;" in icon_block
    assert ".cf-faq-delete-action" in stylesheet
    assert "color: var(--cf-danger);" in css_rule_block(".cf-faq-delete-action")
    assert "background: var(--cf-danger);" in delete_hover_block
    assert "color: #fff;" in delete_hover_block


def test_task_3_appointment_form_cta_matches_create_or_edit_mode():
    template = partial_text("appointment_form.html")

    assert "{% if appointment %}Save Changes{% else %}Create Appointment{% endif %}" in template


def test_appointment_detail_places_add_note_action_on_right():
    template = partial_text("appointment_detail.html")
    note_form_start = template.index("dashboard:add_appointment_note")
    add_note_button = template.index("Add Note</button>", note_form_start)
    wrapper_start = template.rfind("<div", note_form_start, add_note_button)
    wrapper = template[wrapper_start:add_note_button]

    assert 'class="mt-3 flex justify-end"' in wrapper


def test_edit_appointment_form_places_cancel_left_and_save_changes_right():
    template = partial_text("appointment_form.html")
    footer_start = template.index("<div class=\"cf-modal-footer\">")
    footer = template[footer_start : template.index("</div>", footer_start)]

    assert "Cancel</button>" in footer
    assert footer.index("Cancel</button>") < footer.index("{% if appointment %}Save Changes{% else %}Create Appointment{% endif %}</button>")


def test_reschedule_appointment_modal_places_back_left_and_reschedule_right():
    template = partial_text("appointment_detail.html")
    modal_start = template.index("id=\"reschedule-appointment-title\"")
    footer_start = template.index("<div class=\"cf-modal-footer\">", modal_start)
    footer = template[footer_start : template.index("</div>", footer_start)]

    assert footer.index("Back</button>") < footer.index("Reschedule</button>")


def test_edit_patient_modal_places_cancel_left_and_save_changes_right():
    template = partial_text("patient_edit_modal_form.html")
    footer_start = template.index("<div class=\"cf-modal-footer\">")
    footer = template[footer_start : template.index("</div>", footer_start)]

    assert footer.index("Cancel</button>") < footer.index("Save Changes")


ROW_ACTION_TEMPLATE_PATHS = [
    "templates/dashboard/partials/appointment_row.html",
    "templates/dashboard/partials/patient_list.html",
    "templates/dashboard/partials/patient_row.html",
    "templates/dashboard/partials/patient_detail_content.html",
    "templates/dashboard/partials/service_row.html",
    "templates/dashboard/partials/faq_row.html",
    "templates/dashboard/partials/duplicate_list.html",
    "templates/dashboard/settings.html",
    "templates/dashboard/unavailable_dates.html",
]


def test_item_level_action_clusters_match_appointment_button_size():
    for relative_path in ROW_ACTION_TEMPLATE_PATHS:
        template = source_text(relative_path)
        action_blocks = re.findall(
            r"<div\b[^>]*\bcf-row-actions\b[^>]*>.*?</div>",
            template,
            re.DOTALL,
        )
        assert action_blocks, relative_path

        for block in action_blocks:
            for match in re.finditer(
                r"<(?P<tag>a|button)\b(?P<attrs>[^>]*\bclass=\"[^\"]*\bcf-btn\b[^\"]*\"[^>]*)>",
                block,
            ):
                attrs = match.group("attrs")
                if relative_path == "templates/dashboard/partials/duplicate_list.html":
                    assert "cf-btn-sm" in attrs, f"{relative_path}: {match.group(0)}"
                    assert "!min-h-0" not in attrs, f"{relative_path}: {match.group(0)}"
                    continue
                assert "cf-btn-xs" in attrs, f"{relative_path}: {match.group(0)}"
                assert "cf-btn-sm" not in attrs, f"{relative_path}: {match.group(0)}"
                assert "!min-h-0" not in attrs, f"{relative_path}: {match.group(0)}"


def test_item_level_action_icons_use_compact_appointment_size():
    for relative_path in ROW_ACTION_TEMPLATE_PATHS:
        template = source_text(relative_path)
        action_blocks = re.findall(
            r"<div\b[^>]*\bcf-row-actions\b[^>]*>.*?</div>",
            template,
            re.DOTALL,
        )
        assert action_blocks, relative_path

        for block in action_blocks:
            for match in re.finditer(r"<i\b[^>]*data-lucide=\"[^\"]+\"[^>]*>", block):
                icon = match.group(0)
                assert "h-3 w-3" in icon, f"{relative_path}: {icon}"
                assert "shrink-0" in icon, f"{relative_path}: {icon}"
                assert 'aria-hidden="true"' in icon, f"{relative_path}: {icon}"


def test_task_3_appointment_rows_surface_inline_actions():
    template = partial_text("appointment_row.html")
    stylesheet = source_text("static/css/kliniassist.css")
    reschedule_action = css_rule_block(".cf-appointment-reschedule-action")
    reschedule_hover = css_rule_block(".cf-appointment-reschedule-action:hover")

    assert template.count("class=\"cf-btn") == 4
    assert "data-lucide=\"eye\"" in template
    assert "data-lucide=\"pencil\"" in template
    assert "data-lucide=\"calendar-clock\"" in template
    assert "data-lucide=\"x-circle\"" in template
    assert "cf-appointment-row-actions" in template
    for icon in ["eye", "pencil", "calendar-clock", "x-circle"]:
        assert f'data-lucide="{icon}" class="h-3 w-3 shrink-0" aria-hidden="true"' in template
    assert "View</a>" in template
    assert "Edit</a>" in template
    assert "Reschedule</a>" in template
    assert "Cancel</a>" in template
    assert "appointment_edit' appointment.id" in template
    assert "?mode=reschedule" in template
    assert "?mode=cancel" in template
    assert "appointment.status != 'cancelled' and appointment.status != 'completed'" in template
    assert "cf-row-actions" in template
    assert "cf-appointment-action" not in template
    assert ".cf-appointment-action" not in stylesheet
    assert ".cf-btn-xs" in stylesheet
    assert "min-height: 1.75rem;" in stylesheet
    assert "padding: .25rem .55rem;" in stylesheet
    assert "font-size: .6875rem;" in stylesheet
    assert ".cf-row-actions .cf-btn-xs" in stylesheet
    assert "min-height: 1.625rem;" in stylesheet
    assert "padding: .2rem .45rem;" in stylesheet
    assert "width: .75rem;" in stylesheet
    assert "height: .75rem;" in stylesheet
    assert ".cf-row-actions .cf-btn-xs svg" in stylesheet
    assert "width: .7rem;" in stylesheet
    assert "height: .7rem;" in stylesheet
    assert "cf-service-archive-action" not in template
    assert "hx-get=\"{% url 'dashboard:appointment_detail' appointment.id %}\" hx-target=\"#detail-modal-body\" class=\"cf-btn cf-btn-xs cf-appointment-view-action\"" in template
    assert "class=\"cf-btn cf-btn-xs cf-btn-secondary cf-service-edit-action\"" in template
    assert "?mode=reschedule\" hx-target=\"#detail-modal-body\" class=\"cf-btn cf-btn-xs cf-appointment-reschedule-action\"" in template
    assert "Reschedule</a>" in template
    assert "cf-btn-muted" not in template
    assert "class=\"cf-btn cf-btn-xs cf-btn-danger\"" in template
    assert ".cf-appointment-view-action" in stylesheet
    assert ".cf-appointment-view-action:hover" in stylesheet
    assert "background: var(--cf-muted);" in stylesheet
    assert "border-color: var(--cf-muted);" in stylesheet
    assert ".cf-service-edit-action:hover" in stylesheet
    assert "background: var(--cf-brand);" in stylesheet
    assert "background: var(--cf-warning-soft);" in reschedule_action
    assert "color: var(--cf-warning);" in reschedule_action
    assert "background: var(--cf-warning);" in reschedule_hover
    assert "border-color: var(--cf-warning);" in reschedule_hover
    assert "color: #fff;" in reschedule_hover
    assert ".cf-service-archive-action:hover" in stylesheet
    assert ".cf-btn-danger:hover" in stylesheet
    assert "background: var(--cf-danger);" in stylesheet


def test_task_4_dashboard_uses_today_workspace_composition():
    template = dashboard_home_text()

    assert "Today at {{ clinic.name }}" in template or "Today at a glance" in template
    assert "{{ today|date:" in template
    assert "{% now" not in template
    assert "{{ clinic.timezone }}" in template
    assert "New appointment" in template
    assert "Add patient" in template
    assert "View all appointments" not in template
    assert "Needs attention" not in template
    assert "Today's schedule" in template
    assert "{{ appointments|length }} appointments" in template
    assert "Booking widget active" in template
    assert "Smart booking active" not in template
    assert "rocket" not in template
    assert "come to life" not in template


def test_task_4_dashboard_primary_actions_use_get_safe_destinations():
    template = dashboard_home_text()

    assert "{% url 'dashboard:appointments' %}" in template
    assert "{% url 'dashboard:patients' %}" in template
    assert "{% url 'dashboard:create_appointment' %}" not in template
    assert "{% url 'dashboard:create_patient' %}" not in template


def test_task_4_dashboard_primary_kpis_are_appointment_first():
    template = dashboard_home_text()
    labels = ["Today", "Pending", "Open slots", "No-shows"]
    positions = [template.index(f">{label}<") for label in labels]

    assert positions == sorted(positions)
    secondary_labels = ["Upcoming", "Patients", "Completed", "Cancelled"]
    for label in secondary_labels:
        assert template.index(f">{label}<") > positions[-1]


def test_task_4_dashboard_schedule_is_time_first_with_source_payment():
    template = dashboard_home_text()
    headers = re.findall(r"<th\s[^>]*>(.*?)</th>", template, re.DOTALL)
    normalized = [re.sub(r"\s+", " ", header).strip() for header in headers]

    assert normalized[:5] == ["Time", "Patient", "Service", "Source / payment", "Status"]


def test_task_4_dashboard_avoids_legacy_slate_cyan_utilities():
    template = dashboard_home_text()
    legacy_patterns = legacy_utility_patterns()

    for pattern in legacy_patterns:
        assert pattern not in template


def test_patients_page_header_actions_and_search_toolbar_are_consistent():
    template = source_text("templates/dashboard/patients.html")
    header_start = template.index("cf-page-header")
    toolbar_start = template.index("id=\"patient-toolbar\"")
    header_region = template[header_start:toolbar_start]

    assert "cf-page-actions" in header_region
    assert "Check duplicates" in header_region
    assert "Add patient" in header_region
    assert "Check Duplicates" not in header_region
    assert "Add Patient" not in header_region
    assert "hx-get=\"{% url 'dashboard:find_duplicates' %}\"" in header_region
    assert "<button type=\"button\" @click=\"patientOpen=true\"" in header_region

    toolbar_match = re.search(
        r"<form id=\"patient-toolbar\"(?P<attrs>[^>]*)>(?P<body>.*?)</form>",
        template,
        re.DOTALL,
    )

    assert toolbar_match is not None
    toolbar_attrs = toolbar_match.group("attrs")
    toolbar_body = toolbar_match.group("body")
    assert "class=\"cf-toolbar\"" in toolbar_attrs
    search_group_match = re.search(
        r"<div class=\"(?P<class>[^\"]*)\">\s*<label[^>]*for=\"patient-search\"[^>]*class=\"cf-label\"[^>]*>Search</label>\s*<input[^>]*id=\"patient-search\"[^>]*name=\"q\"[^>]*class=\"(?P<input_class>[^\"]*)\"",
        toolbar_body,
        re.DOTALL,
    )
    assert search_group_match is not None
    search_group_class = search_group_match.group("class")
    assert "cf-field" in search_group_class
    assert "w-80" in search_group_class
    assert "sm:w-96" in search_group_class
    assert "lg:w-[28rem]" in search_group_class
    assert "shrink-0" in search_group_class
    input_class = search_group_match.group("input_class")
    assert "cf-input" in input_class
    assert "max-w-2xl" not in input_class
    assert "flex-1" not in input_class
    input_match = re.search(r"<input[^>]*name=\"q\"", toolbar_body, re.DOTALL)
    assert input_match is not None
    assert "hx-get=\"{% url 'dashboard:patients' %}\"" in toolbar_body
    assert "Check duplicates" not in toolbar_body
    assert "Add patient" not in toolbar_body
    assert '<div id="duplicate-panel" class="cf-async-panel"></div>' in template


def test_services_page_header_action_uses_sentence_case():
    template = source_text("templates/dashboard/services.html")
    header_region = div_block_containing(template, "cf-page-header")

    assert "Add service" in header_region
    assert "Add Service" not in header_region


def test_task_5_appointment_filters_and_status_dropdown_use_design_system():
    template = source_text("templates/dashboard/appointments.html")

    assert "id=\"filter-form\" class=\"cf-toolbar" in template
    for filter_id in ["filter-status", "filter-date-from", "filter-date-to", "filter-service", "filter-source", "filter-payment", "filter-search"]:
        assert f"for=\"{filter_id}\"" in template
        assert f"id=\"{filter_id}\"" in template
    for snippet in [
        "class=\"cf-field\"",
        "class=\"cf-label\"",
        "class=\"cf-input\"",
        "class=\"cf-select\"",
    ]:
        assert snippet in template

    filter_form = template[template.index("<form id=\"filter-form\" class=\"cf-toolbar\">") : template.index("<div id=\"appointments-table\"")]
    for preserved_filter in ["status", "date_from", "date_to", "service", "source", "payment_state", "q"]:
        assert preserved_filter in filter_form
    assert "<select id=\"filter-status\" name=\"status\"" in filter_form
    assert "<option value=\"\">All Statuses</option>" in filter_form
    assert "{% if status == value %}selected{% endif %}" in filter_form
    assert filter_form.index("id=\"filter-search\"") < filter_form.index("id=\"filter-status\"")
    assert "class=\"cf-field w-full\"" not in filter_form
    assert "<div class=\"basis-full\">" not in filter_form
    assert "<div class=\"cf-field w-80 md:w-96\">\n      <label for=\"filter-search\"" in filter_form
    assert "<input id=\"filter-search\" type=\"search\" name=\"q\" value=\"{{ search_query }}\"" in filter_form
    assert "Search patient, phone, service, or reference" in filter_form
    assert "hx-trigger=\"input changed delay:300ms, search\"" in filter_form
    assert "href=\"?status={{ value }}\"" not in filter_form
    assert "hx-push-url=\"true\"" in template
    assert "type=\"hidden\" name=\"status\"" not in template
    assert ":href=\"exportHref()\"" in template
    assert "statusHref(" not in template


def test_task_5_appointment_table_surfaces_payment_status():
    appointment_list = partial_text("appointment_list.html")
    appointment_row = partial_text("appointment_row.html")

    headers = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", appointment_list, re.DOTALL)
    normalized = [re.sub(r"\s+", " ", header).strip() for header in headers]

    assert "Payment" in normalized
    assert "{{ appointment.get_payment_state_display }}" in appointment_row
    assert "colspan=\"7\"" in appointment_list


def test_task_5_appointment_pagination_preserves_filters_for_htmx():
    appointment_list = partial_text("appointment_list.html")

    assert "hx-get=\"{% url 'dashboard:appointments' %}\"" not in appointment_list
    for page_snippet in [
        "hx-get=\"?page=1",
        "hx-get=\"?page={{ page_obj.previous_page_number }}",
        "hx-get=\"?page={{ num }}",
        "hx-get=\"?page={{ page_obj.next_page_number }}",
        "hx-get=\"?page={{ page_obj.paginator.num_pages }}",
    ]:
        assert page_snippet in appointment_list
    assert "{% if search_query %}&q={{ search_query|urlencode }}{% endif %}" in appointment_list


def test_patient_pagination_preserves_search_for_htmx():
    patient_list = partial_text("patient_list.html")

    for page_snippet in [
        "hx-get=\"?page=1",
        "hx-get=\"?page={{ page_obj.previous_page_number }}",
        "hx-get=\"?page={{ num }}",
        "hx-get=\"?page={{ page_obj.next_page_number }}",
        "hx-get=\"?page={{ page_obj.paginator.num_pages }}",
    ]:
        assert page_snippet in patient_list
    assert "{% if query %}&q={{ query|urlencode }}{% endif %}" in patient_list
    assert "hx-target=\"#patient-list\"" in patient_list
    assert "hx-push-url=\"true\"" in patient_list


def test_appointment_search_preserves_input_focus_after_htmx_swap():
    appointments = source_text("templates/dashboard/appointments.html")
    base = dashboard_base_text()
    search_input = re.search(r"<input id=\"filter-search\"[^>]+>", appointments)

    assert search_input is not None
    assert 'data-cf-preserve-focus="true"' in search_input.group(0)
    assert "requestElt.closest('[data-cf-preserve-focus=\"true\"]')" in base
    assert "if (preserveFocus) {" in base
    assert "return;" in base[base.index("if (preserveFocus) {") : base.index("var target = evt.detail.elt;")]


def test_patient_search_preserves_input_focus_after_htmx_swap():
    patients = source_text("templates/dashboard/patients.html")
    base = dashboard_base_text()
    search_input = re.search(r"<input id=\"patient-search\"[^>]+>", patients)

    assert search_input is not None
    assert 'data-cf-preserve-focus="true"' in search_input.group(0)
    assert "requestElt.closest('[data-cf-preserve-focus=\"true\"]')" in base


def test_task_5_appointment_modals_use_neon_aqua_anatomy_and_singular_titles():
    appointments = source_text("templates/dashboard/appointments.html")
    detail = partial_text("appointment_detail.html")
    form = partial_text("appointment_form.html")

    for template in [appointments, detail]:
        assert "cf-modal-header" in template
        assert "cf-modal-title" in template
        assert "cf-modal-body" in template
        assert "cf-modal-footer" in template

    assert "role=\"dialog\"" in appointments
    assert "aria-modal=\"true\"" in appointments
    assert "aria-labelledby=" in appointments
    assert "role=\"dialog\"" not in detail

    assert "Add appointment" in appointments
    assert "{% if appointment %}Edit appointment{% else %}Add appointment{% endif %}" in form
    assert "id=\"{% if appointment %}appointment-detail-title{% else %}add-appointment-title{% endif %}\"" in form
    assert "Cancel appointment" in detail
    assert "Reschedule appointment" in detail
    assert "Delete appointment" in detail
    assert "id=\"appointment-detail-title\" class=\"sr-only\"" in detail
    assert "mode === 'cancel' ? 'Cancel appointment'" in detail
    assert "mode === 'reschedule' ? 'Reschedule appointment'" in detail
    assert "mode === 'delete' ? 'Delete appointment'" in detail
    assert "name=\"modal_source\" value=\"{{ source }}\"" in detail
    assert "source == 'calendar'" in detail
    assert "appointment_edit' appointment.id" not in detail
    assert "@click=\"mode = 'reschedule'\"" in detail
    assert "@click=\"mode = 'cancel'\"" in detail
    assert "@click=\"mode = 'delete'\"" in detail
    assert "hx-target=\"#cancel-error\"" in detail
    assert "hx-swap=\"innerHTML\"" in detail
    assert "id=\"cancel-error\"" in detail
    assert "@htmx:after-request=\"detailOpen = false\"" not in detail
    assert "$event.detail.successful" not in detail
    assert detail.count("getResponseHeader('HX-Trigger')") >= 2
    assert "Add Appointment" not in appointments
    assert "Edit Appointments" not in form
    assert "Add Appointments" not in form
    assert "@click=\"patientOpen=true\"" not in appointments
    assert "open=false; patientOpen=true" in appointments
    assert "detailOpen=false; patientOpen=true" in form
    assert "{% if source != 'calendar' %}" in form
    assert "trapModalFocus" in appointments
    assert "@keydown.tab=\"trapModalFocus($event, $el)\"" in appointments
    assert "Cancel Appointments" not in detail
    assert "Reschedule Appointments" not in detail


def test_add_appointment_modal_places_cancel_action_on_left():
    template = source_text("templates/dashboard/appointments.html")
    modal_start = template.index("id=\"add-appointment-title\"")
    footer_start = template.index("<div class=\"cf-modal-footer\">", modal_start)
    footer = template[footer_start : template.index("</div>", footer_start)]

    assert footer.index("Cancel</button>") < footer.index("Create appointment</button>")


def test_cancel_appointment_modal_places_confirm_cancel_action_on_right():
    template = partial_text("appointment_detail.html")
    cancel_start = template.index("<!-- Cancel Mode -->")
    cancel_end = template.index("<!-- Reschedule Mode -->", cancel_start)
    cancel_mode = template[cancel_start:cancel_end]
    footer_start = cancel_mode.index("<div class=\"cf-modal-footer\">")
    footer = cancel_mode[footer_start : cancel_mode.index("</div>", footer_start)]

    assert footer.index("Back</button>") < footer.index("Confirm Cancel</button>")


def test_task_5_calendar_uses_single_neon_aqua_shell_and_accessible_modal():
    template = source_text("templates/dashboard/calendar.html")

    assert "class=\"cf-card" in template
    assert "id=\"calendar\"" in template
    assert "id=\"calendar-title\"" in template
    assert "cf-calendar-header" in template
    assert "cf-calendar-nav" in template
    assert "cf-calendar-views" in template
    assert "cf-calendar-legend" in template
    assert "id=\"calendar-toolbar\" class=\"cf-toolbar\"" in template
    assert "updateCalendarTitle" in template
    assert "datesSet" in template
    assert "id=\"filter-service\"" in template
    assert "id=\"filter-status\"" in template
    assert "id=\"calendar-prev\"" in template
    assert "id=\"calendar-next\"" in template
    assert "id=\"calendar-today\"" in template
    assert "data-calendar-view=\"dayGridMonth\"" in template
    assert "data-calendar-view=\"timeGridWeek\"" in template
    assert "data-calendar-view=\"timeGridDay\"" in template
    assert "href=\"{% url 'dashboard:appointments' %}\"" in template
    assert "Add appointment" in template
    assert "href=\"{% url 'dashboard:appointments' %}\" class=\"cf-btn cf-btn-primary\"" in template
    assert "data-lucide=\"calendar-plus\"" in template
    assert "href=\"{% url 'dashboard:appointments' %}\" class=\"cf-btn cf-btn-primary cf-btn-sm\"" not in template
    assert "class=\"cf-field\"" in template
    assert "class=\"cf-label\"" in template
    assert "class=\"cf-select" in template
    assert "cf-status-booked" in template
    assert "cf-status-confirmed" in template
    assert "cf-status-completed" in template
    assert "cf-status-cancelled" in template
    assert "cf-status-no-show" in template
    assert template.count("cf-card") == 1
    assert "headerToolbar: false" in template
    assert "role=\"dialog\"" in template
    assert "aria-modal=\"true\"" in template
    assert "aria-labelledby=\"appointment-detail-title\"" in template
    assert "id=\"appointment-detail-title\"" in template
    assert "calendar-detail-title" not in template
    assert "toast-message" in template
    assert "Appointment rescheduled successfully." in template
    assert "window.confirm" in template
    assert "id=\"calendar-loading\"" in template
    assert "role=\"status\"" in template
    assert "aria-live=\"polite\"" in template
    assert "setCalendarBusy(true)" in template
    assert "setCalendarBusy(false)" in template
    assert "trapCalendarFocus" in template
    assert "@keydown.tab=\"trapCalendarFocus($event, $el)\"" in template
    assert "querySelectorAll(`a[href]" in template
    assert "[tabindex]:not([tabindex='-1'])" in template
    assert "[tabindex]:not([tabindex=\\\"-1\\\"])" not in template
    assert "if (!response.ok)" in template
    assert "Calendar events request failed." in template

    tools_index = template.index("id=\"calendar-toolbar\"")
    card_index = template.index("class=\"cf-card cf-calendar-card")
    header_index = template.index("class=\"cf-calendar-header\"")
    grid_index = template.index("<div id=\"calendar\"")
    assert tools_index < card_index < header_index < grid_index


def test_task_5_calendar_css_supports_reference_grid_layout():
    css = css_text()

    for selector in [
        ".cf-calendar-card",
        ".cf-calendar-header",
        ".cf-calendar-nav",
        ".cf-calendar-views",
        ".cf-calendar-title",
        ".cf-calendar-filters",
        ".cf-calendar-legend",
        "#calendar .fc-col-header-cell-cushion",
        "#calendar .fc-daygrid-day-number",
        "#calendar .fc-daygrid-day-frame",
        "#calendar .fc-event",
    ]:
        assert selector in css

    header = css_rule_block(".cf-calendar-header")
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in header

    title = css_rule_block(".cf-calendar-title")
    assert "text-align: center" in title
    assert "white-space: nowrap" in title

    event = css_rule_block("#calendar .fc-event")
    assert "border-radius: var(--cf-radius-sm)" in event


def test_task_5_appointments_and_calendar_avoid_replaced_legacy_utilities():
    legacy_patterns = legacy_utility_patterns(include_font_weight=True)

    for relative_path in ["templates/dashboard/appointments.html", "templates/dashboard/calendar.html"]:
        template = source_text(relative_path)
        for pattern in legacy_patterns:
            assert pattern not in template


def test_task_9_widget_templates_avoid_legacy_slate_cyan_utilities():
    legacy_patterns = legacy_utility_patterns()

    for relative_path in [
        "templates/widget/widget.html",
        "templates/widget/partials/slots.html",
        "templates/widget/partials/booking_success.html",
        "templates/widget/partials/booking_error.html",
        "templates/widget/booking_success.html",
    ]:
        template = source_text(relative_path)
        for pattern in legacy_patterns:
            assert pattern not in template


def test_task_9_widget_preserves_behavior_hooks_and_neon_aqua_patterns():
    widget = source_text("templates/widget/widget.html")
    slots = source_text("templates/widget/partials/slots.html")
    partial_success = source_text("templates/widget/partials/booking_success.html")
    full_success = source_text("templates/widget/booking_success.html")

    for snippet in [
        'x-data="widgetApp()"',
        'id="slots-container"',
        'hx-get="{% url \'widget:slots\' clinic.slug %}"',
        'hx-target="#slots-container"',
        'id="booking-form-container"',
        'hx-target="#booking-form-container"',
        "accentColor: '{{ clinic.safe_widget_accent_color|escapejs }}'",
        "kliniassist-minimize",
        "htmx:beforeSwap",
    ]:
        assert snippet in widget

    assert "cf-gradient-mesh" in widget or "cf-gradient-mesh" in partial_success or "cf-gradient-mesh" in full_success

    for snippet in [
        "data-slot-value",
        '@click="selectSlot(',
        "cf-slot-button",
        "'background-color:' + accentColor",
    ]:
        assert snippet in slots


def test_mobile_responsive_css_scopes_full_width_buttons_and_keeps_tap_targets():
    mobile = css_media_block("max-width: 640px")

    for rule in re.finditer(r"(?ms)^(?P<selectors>[^{}]+)\{(?P<body>.*?)^\s*\}", mobile):
        selectors = [selector.strip() for selector in rule.group("selectors").split(",")]
        if ".cf-btn" in selectors:
            assert "width: 100%;" not in rule.group("body")
    full_width_rule = re.search(
        r"(?ms)^\s*\.cf-page-actions \.cf-btn,\s*^\s*\.cf-toolbar \.cf-btn,\s*^\s*\.cf-modal-footer \.cf-btn\s*\{(?P<body>.*?)^\s*\}",
        mobile,
    )
    assert full_width_rule is not None
    assert "width: 100%;" in full_width_rule.group("body")

    auto_width_rule = re.search(
        r"(?ms)^\s*\.cf-table \.cf-btn,\s*^\s*\.cf-row-actions \.cf-btn,\s*^\s*\.cf-btn-sm,\s*^\s*\.cf-btn-xs\s*\{(?P<body>.*?)^\s*\}",
        mobile,
    )
    assert auto_width_rule is not None
    assert "width: auto;" in auto_width_rule.group("body")

    assert "min-height: 2.5rem;" in css_rule_block(".cf-btn-sm")
    assert "min-height: 1.75rem;" in css_rule_block(".cf-btn-xs")
    assert "min-height: 1.625rem;" in css_rule_block(".cf-row-actions .cf-btn-xs")
    assert "min-height: 2.75rem;" in css_rule_block(".cf-slot-button")


def test_mobile_responsive_dashboard_shell_and_pagination_avoid_overlap_and_overflow():
    base = dashboard_base_text()
    appointment_list = partial_text("appointment_list.html")

    assert "pb-24 md:px-8 md:pt-5 md:pb-12" in base
    assert "grid h-10 w-10 place-items-center" in base
    assert "flex flex-col gap-3 px-5 py-4 border-t border-[var(--cf-line)] sm:flex-row sm:items-center sm:justify-between" in appointment_list
    assert "class=\"flex flex-wrap justify-center gap-1 sm:justify-end\"" in appointment_list


def test_mobile_responsive_calendar_and_widget_use_safe_viewports():
    calendar = source_text("templates/dashboard/calendar.html")
    widget = source_text("templates/widget/widget.html")
    embed_js = source_text("widget/views.py")
    widget_embed = source_text("templates/dashboard/widget_embed.html")

    assert "const calendarScreen = window.matchMedia('(max-width: 768px)');" in calendar
    assert "const isPhone = () => calendarScreen.matches;" in calendar
    assert "initialView: 'dayGridMonth'" in calendar
    assert "initialView: isPhone() ? 'timeGridDay' : 'dayGridMonth'" not in calendar
    assert "dayMaxEvents: isPhone() ? 2 : 5" in calendar
    assert "syncCalendarViewport();" in calendar
    assert "max-h-[calc(100dvh-1rem)]" in widget
    assert "bottom:max(16px, env(safe-area-inset-bottom))" in embed_js
    assert "right:max(16px, env(safe-area-inset-right))" in embed_js
    assert "max-height:calc(100dvh - 32px - env(safe-area-inset-bottom))" in embed_js
    assert "max-height:calc(100dvh - 32px - env(safe-area-inset-bottom))" in widget_embed


def test_mobile_responsive_dynamic_text_has_wrapping_guards():
    assistant_settings = source_text("templates/dashboard/assistant_settings.html")
    widget_embed = source_text("templates/dashboard/widget_embed.html")
    duplicate_list = partial_text("duplicate_list.html")
    merge_confirm = partial_text("merge_confirm.html")
    faq_row = partial_text("faq_row.html")
    appointment_detail = partial_text("appointment_detail.html")
    patient_list = partial_text("patient_list.html")
    widget = source_text("templates/widget/widget.html")
    partial_success = source_text("templates/widget/partials/booking_success.html")
    full_success = source_text("templates/widget/booking_success.html")

    assert "block min-w-0 max-w-full flex-1 break-all" in widget_embed
    assert "flex flex-col gap-3 rounded-[var(--cf-radius)] border border-[var(--cf-line-soft)] p-4 sm:flex-row sm:items-center sm:justify-between" in duplicate_list
    assert "min-w-0 break-words text-sm" in duplicate_list
    assert "flex flex-col gap-3 sm:flex-row sm:items-center" in merge_confirm
    assert "cf-faq-card" in faq_row
    assert "min-w-0" in faq_row
    assert "break-words" in faq_row
    assert "whitespace-pre-wrap" in faq_row
    assert "cf-faq-layout" in assistant_settings
    assert "break-all" in appointment_detail
    assert "max-w-[14rem] break-all" in patient_list
    assert "min-w-0 flex-1" in widget
    assert "break-words" in widget
    for template in [partial_success, full_success]:
        assert "justify-between gap-3" in template
        assert "min-w-0 text-right break-words" in template


def test_settings_page_level_save_buttons_align_right():
    assistant_settings = source_text("templates/dashboard/assistant_settings.html")
    widget_embed = source_text("templates/dashboard/widget_embed.html")
    settings = source_text("templates/dashboard/settings.html")
    business_hours = source_text("templates/dashboard/business_hours.html")
    slot_preview = source_text("templates/dashboard/slot_preview.html")

    page_level_save_blocks = [
        div_block_containing(assistant_settings, "Save Assistant Settings"),
        div_block_containing(widget_embed, "Save Changes"),
        div_block_containing(settings, "Save Changes"),
        div_block_containing(settings, "Save Business Hours"),
        div_block_containing(settings, "Preview Slots"),
        div_block_containing(business_hours, "Save Business Hours"),
        div_block_containing(slot_preview, "Preview Slots"),
    ]

    for block in page_level_save_blocks:
        assert "justify-end" in block


def test_unavailable_date_modals_use_existing_two_action_footer_pattern():
    templates = [
        source_text("templates/dashboard/settings.html"),
        source_text("templates/dashboard/unavailable_dates.html"),
    ]

    for template in templates:
        footer = div_block_containing(template, "Save Unavailable Date")

        assert "cf-modal-footer" in footer
        assert "cf-btn cf-btn-secondary flex-1" in footer
        assert "Cancel" in footer
        assert "cf-btn cf-btn-primary flex-1" in footer
        assert "Save Unavailable Date" in footer
        assert "cf-btn cf-btn-primary w-full" not in footer


def test_unavailable_date_modals_keep_fields_full_width():
    fields = [
        (source_text("templates/dashboard/settings.html"), "settings-unavailable-date", "settings-unavailable-reason"),
        (source_text("templates/dashboard/unavailable_dates.html"), "unavailable-date-date", "unavailable-date-reason"),
    ]

    for template, date_input_id, reason_input_id in fields:
        date_field = div_block_containing(template, date_input_id)
        reason_field = div_block_containing(template, reason_input_id)

        assert "cf-field" in date_field
        assert "md:col-span-2" in date_field
        assert "md:col-span-2" in reason_field

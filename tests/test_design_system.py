from pathlib import Path
import re


CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "css" / "clinicflow.css"
DASHBOARD_BASE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "base.html"
DASHBOARD_HOME_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "home.html"
SEARCH_RESULTS_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "partials" / "search_results.html"
ROOT = Path(__file__).resolve().parents[1]
PARTIALS_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard" / "partials"


def css_text():
    return CSS_PATH.read_text(encoding="utf-8")


def dashboard_base_text():
    return DASHBOARD_BASE_PATH.read_text(encoding="utf-8")


def dashboard_home_text():
    return DASHBOARD_HOME_PATH.read_text(encoding="utf-8")


def search_results_text():
    return SEARCH_RESULTS_PATH.read_text(encoding="utf-8")


def source_text(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


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


def test_outline_buttons_keep_brand_hover_state():
    css = css_text()
    hover_block = css_rule_block(".cf-btn-secondary:hover,\n.ui-button-secondary:hover")

    assert "background: var(--cf-brand-soft);" in hover_block
    assert "border-color: var(--cf-brand-hover);" in hover_block
    assert "color: var(--cf-brand-hover);" in hover_block

    for match in re.finditer(r"(?ms)^[^{]*cf-btn-secondary:hover[^{]*\{(?P<body>.*?)^\}", css):
        assert "var(--cf-surface-warm)" not in match.group("body")


def test_css_contains_cards_tables_and_badges():
    css = css_text()

    for selector in [
        ".cf-card",
        ".cf-card-muted",
        ".cf-kpi",
        ".cf-table-wrap",
        ".cf-table-header",
        ".cf-table",
        ".cf-row-actions",
        ".cf-badge",
    ]:
        assert selector in css

    table_wrap = css_rule_block(".cf-table-wrap")
    assert "overflow-x: auto;" in table_wrap
    assert "overflow-y: hidden;" in table_wrap


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
    assert "min-width: 720px;" in css_rule_block(".cf-table")
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
    assert "label=\"Booking Widget\"" in template
    assert 'url_name="dashboard:billing"' in setup_group
    assert "icon=\"message-circle\" label=\"Booking Widget\"" in template
    assert "<span>Overview</span>" in template
    assert "label=\"Dashboard\"" not in template
    assert "label=\"Assistant\"" not in template
    assert "<span>Home</span>" not in template
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


def test_billing_page_shows_dummy_monthly_plan_prices():
    template = source_text("templates/dashboard/billing.html")

    assert "₱999/mo" in template
    assert "₱1,999/mo" in template


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
        assert "overflow-x-auto" in template
        assert "cf-table" in template


def test_patient_empty_search_keeps_table_heading_and_columns_visible():
    template = partial_text("patient_list.html")

    assert "{% empty %}" in template
    assert '<td colspan="6">' in template
    assert template.index("cf-table-header") < template.index("<thead")
    assert template.index("<thead") < template.index("{% empty %}")
    assert template.index("{% empty %}") < template.index("No patients found")
    assert "cf-card cf-empty-state" not in template


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


def test_service_row_toggle_button_uses_stateful_action_styles():
    template = partial_text("service_row.html")
    muted_button = css_rule_block(".cf-btn-muted")
    edit_hover = css_rule_block(".cf-service-edit-action:hover")
    archive_hover = css_rule_block(".cf-service-archive-action:hover")

    assert 'class="cf-btn cf-btn-sm cf-btn-secondary cf-service-edit-action"' in template
    assert 'class="cf-btn cf-btn-sm cf-btn-muted cf-service-archive-action"' in template
    assert "cf-btn cf-btn-sm {% if service.is_active %}cf-btn-danger{% else %}cf-btn-primary{% endif %}" in template
    assert '{{ service.is_active|yesno:"Deactivate,Activate" }}' in template
    assert "border-color:" in muted_button
    assert "background: var(--cf-surface);" in muted_button
    assert "var(--cf-brand)" not in muted_button
    assert "var(--cf-danger)" not in muted_button
    assert "background: var(--cf-brand);" in edit_hover
    assert "border-color: var(--cf-brand);" in edit_hover
    assert "color: #fff;" in edit_hover
    assert "background: var(--cf-ink-secondary);" in archive_hover
    assert "border-color: var(--cf-ink-secondary);" in archive_hover
    assert "color: #fff;" in archive_hover


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


def test_task_3_faq_row_controls_are_accessible():
    template = partial_text("faq_row.html")

    assert "for=\"faq-question-{{ faq.id }}\"" in template
    assert "id=\"faq-question-{{ faq.id }}\"" in template
    assert "for=\"faq-answer-{{ faq.id }}\"" in template
    assert "id=\"faq-answer-{{ faq.id }}\"" in template
    assert "aria-label=\"{% if faq.is_active %}Deactivate FAQ{% else %}Activate FAQ{% endif %}\"" in template
    assert "aria-label=\"Edit FAQ\"" in template
    assert "aria-label=\"Delete FAQ\"" in template


def test_task_3_appointment_form_cta_matches_create_or_edit_mode():
    template = partial_text("appointment_form.html")

    assert "{% if appointment %}Save Changes{% else %}Create Appointment{% endif %}" in template


def test_task_3_appointment_rows_surface_inline_actions():
    template = partial_text("appointment_row.html")
    stylesheet = source_text("static/css/clinicflow.css")

    assert template.count("class=\"cf-btn") == 4
    assert "data-lucide=\"eye\"" in template
    assert "data-lucide=\"pencil\"" in template
    assert "data-lucide=\"calendar-clock\"" in template
    assert "data-lucide=\"x-circle\"" in template
    for icon in ["eye", "pencil", "calendar-clock", "x-circle"]:
        assert f'data-lucide="{icon}" class="h-4 w-4 shrink-0" aria-hidden="true"' in template
    assert "View</a>" in template
    assert "Edit</a>" in template
    assert "Reschedule</a>" in template
    assert "Cancel</a>" in template
    assert "appointment_edit' appointment.id" in template
    assert "?mode=reschedule" in template
    assert "?mode=cancel" in template
    assert "appointment.status != 'cancelled' and appointment.status != 'completed'" in template
    assert "cf-appointment-action" not in template
    assert ".cf-appointment-action" not in stylesheet
    assert ".cf-btn-xs" in stylesheet
    assert "min-height: 2.5rem;" in stylesheet
    assert template.count("cf-service-archive-action") == 1
    assert "hx-get=\"{% url 'dashboard:appointment_detail' appointment.id %}\" hx-target=\"#detail-modal-body\" class=\"cf-btn cf-btn-xs cf-appointment-view-action\"" in template
    assert "class=\"cf-btn cf-btn-xs cf-btn-muted cf-service-archive-action\"" in template
    assert "class=\"cf-btn cf-btn-xs cf-btn-secondary cf-service-edit-action\"" in template
    assert "class=\"cf-btn cf-btn-xs cf-btn-muted cf-service-archive-action\"" in template
    assert "class=\"cf-btn cf-btn-xs cf-btn-danger\"" in template
    assert ".cf-appointment-view-action" in stylesheet
    assert ".cf-appointment-view-action:hover" in stylesheet
    assert "background: var(--cf-muted);" in stylesheet
    assert "border-color: var(--cf-muted);" in stylesheet
    assert ".cf-service-edit-action:hover" in stylesheet
    assert "background: var(--cf-brand);" in stylesheet
    assert ".cf-service-archive-action:hover" in stylesheet
    assert "background: var(--cf-ink-secondary);" in stylesheet
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
    assert "Needs attention" in template
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

    filter_form = template[template.index("<form id=\"filter-form\" class=\"cf-toolbar\">") : template.index("<div id=\"appointments-table\">")]
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
    assert "{% if search_query %}&q={{ search_query }}{% endif %}" in appointment_list


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
    assert "id=\"appointment-detail-title\" class=\"sr-only\"" in detail
    assert "x-text=\"mode === 'cancel' ? 'Cancel appointment'" in detail
    assert "name=\"modal_source\" value=\"calendar\"" in detail
    assert "source == 'calendar'" in detail
    assert "appointment_edit' appointment.id" not in detail
    assert "@click=\"mode = 'reschedule'\"" not in detail
    assert "@click=\"mode = 'cancel'\"" not in detail
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
        "clinicflow-minimize",
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
    css = css_text()
    mobile = re.search(r"@media \(max-width: 640px\) \{(?P<body>.*?)^\}", css, re.DOTALL | re.MULTILINE).group("body")

    assert re.search(r"(?m)^\s*\.cf-btn\s*\{\s*width:\s*100%;\s*\}", mobile) is None
    for snippet in [
        ".cf-page-actions .cf-btn",
        ".cf-toolbar .cf-btn",
        ".cf-modal-footer .cf-btn",
        ".cf-table .cf-btn",
        ".cf-row-actions .cf-btn",
        "width: auto;",
    ]:
        assert snippet in mobile

    assert "min-height: 2.5rem;" in css_rule_block(".cf-btn-sm")
    assert "min-height: 2.5rem;" in css_rule_block(".cf-btn-xs")
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
    assistant_settings = source_text("templates/dashboard/assistant_settings.html")
    widget_embed = source_text("templates/dashboard/widget_embed.html")

    assert "const isSmallScreen = window.matchMedia('(max-width: 640px)').matches;" in calendar
    assert "initialView: isSmallScreen ? 'timeGridDay' : 'dayGridMonth'" in calendar
    assert "dayMaxEvents: isSmallScreen ? 2 : 5" in calendar
    assert "max-h-[calc(100dvh-1rem)]" in widget
    assert "bottom:max(16px, env(safe-area-inset-bottom))" in embed_js
    assert "right:max(16px, env(safe-area-inset-right))" in embed_js
    assert "max-height:calc(100dvh - 32px - env(safe-area-inset-bottom))" in embed_js
    assert "max-height:calc(100dvh - 32px - env(safe-area-inset-bottom))" in assistant_settings
    assert "max-height:calc(100dvh - 32px - env(safe-area-inset-bottom))" in widget_embed


def test_mobile_responsive_dynamic_text_has_wrapping_guards():
    assistant_settings = source_text("templates/dashboard/assistant_settings.html")
    duplicate_list = partial_text("duplicate_list.html")
    merge_confirm = partial_text("merge_confirm.html")
    faq_row = partial_text("faq_row.html")
    appointment_detail = partial_text("appointment_detail.html")
    patient_list = partial_text("patient_list.html")
    widget = source_text("templates/widget/widget.html")
    partial_success = source_text("templates/widget/partials/booking_success.html")
    full_success = source_text("templates/widget/booking_success.html")

    assert "block min-w-0 max-w-full flex-1 break-all" in assistant_settings
    assert "flex flex-col gap-3 rounded-[var(--cf-radius)] border border-[var(--cf-line-soft)] p-4 sm:flex-row sm:items-center sm:justify-between" in duplicate_list
    assert "min-w-0 break-words text-sm" in duplicate_list
    assert "flex flex-col gap-3 sm:flex-row sm:items-center" in merge_confirm
    assert "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between" in faq_row
    assert "break-words" in faq_row
    assert "break-all" in appointment_detail
    assert "max-w-[14rem] break-all" in patient_list
    assert "min-w-0 flex-1" in widget
    assert "break-words" in widget
    for template in [partial_success, full_success]:
        assert "justify-between gap-3" in template
        assert "min-w-0 text-right break-words" in template

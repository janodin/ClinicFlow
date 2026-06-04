# Patient Table Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Appointments-style pagination to the dashboard Patients table.

**Architecture:** The Patients view will paginate the clinic-scoped patient queryset with Django's `Paginator`, then pass the current page as `patients` and `page_obj`. The Patients partial will render a pager matching the Appointments partial, preserving the search query through normal links and HTMX requests.

**Tech Stack:** Django views/templates, Django `Paginator`, HTMX, pytest.

---

## File Structure

- Modify: `dashboard/tests.py` for behavior tests covering 10-row patient pagination.
- Modify: `tests/test_design_system.py` for template tests covering HTMX/search-preserving pagination controls.
- Modify: `dashboard/views.py` for patient queryset pagination.
- Modify: `templates/dashboard/patients.html` so the page header reports total records, not only current-page length.
- Modify: `templates/dashboard/partials/patient_list.html` for Appointments-style pagination markup.

### Task 1: Add Failing Behavior Test For Patients Pagination

**Files:**
- Modify: `dashboard/tests.py`

- [ ] **Step 1: Write the failing test**

Add this test after `test_patients_list_orders_latest_created_first`:

```python
@pytest.mark.django_db
def test_patients_page_paginates_ten_patients(clinic_setup, client):
    clinic, service, user = clinic_setup
    client.force_login(user)

    for index in range(11):
        Patient.objects.create(
            clinic=clinic,
            full_name=f"Paged Patient {index:02d}",
            phone=f"0917001{index:04d}",
        )

    response = client.get(reverse("dashboard:patients"))
    page_obj = response.context["page_obj"]

    assert response.status_code == 200
    assert page_obj.paginator.per_page == 10
    assert len(page_obj.object_list) == 10
    assert page_obj.paginator.num_pages == 2
    assert list(response.context["patients"]) == list(page_obj)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\env\Scripts\python -m pytest dashboard/tests.py::test_patients_page_paginates_ten_patients -v`

Expected: FAIL because `response.context["page_obj"]` does not exist yet for Patients.

### Task 2: Add Failing Template Test For Patient Pagination Links

**Files:**
- Modify: `tests/test_design_system.py`

- [ ] **Step 1: Write the failing template test**

Add this test near `test_task_5_appointment_pagination_preserves_filters_for_htmx`:

```python
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
    assert "{% if query %}&q={{ query }}{% endif %}" in patient_list
    assert "hx-target=\"#patient-list\"" in patient_list
    assert "hx-push-url=\"true\"" in patient_list
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\env\Scripts\python -m pytest tests/test_design_system.py::test_patient_pagination_preserves_search_for_htmx -v`

Expected: FAIL because `patient_list.html` has no pagination markup yet.

### Task 3: Implement View Pagination

**Files:**
- Modify: `dashboard/views.py:671-680`

- [ ] **Step 1: Write minimal implementation**

Replace the current `patients` view body with:

```python
@login_required
def patients(request):
    clinic = _clinic_or_redirect(request)
    query = request.GET.get("q", "").strip()
    qs = clinic.patients.order_by("-created_at", "-id")
    if query:
        qs = qs.filter(Q(full_name__icontains=query) | Q(phone__icontains=query) | Q(email__icontains=query))
    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    context = {
        "clinic": clinic,
        "patients": page_obj,
        "page_obj": page_obj,
        "patient_form": PatientForm(clinic=clinic),
        "query": query,
    }
    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/patient_list.html", context)
    return render(request, "dashboard/patients.html", context)
```

- [ ] **Step 2: Run behavior tests**

Run: `.\env\Scripts\python -m pytest dashboard/tests.py::test_patients_list_orders_latest_created_first dashboard/tests.py::test_patients_page_paginates_ten_patients -v`

Expected: PASS. The existing ordering test should still pass because Django `Page` objects are iterable.

### Task 4: Add Appointments-Style Patient Pagination Markup

**Files:**
- Modify: `templates/dashboard/patients.html:6`
- Modify: `templates/dashboard/partials/patient_list.html:58`

- [ ] **Step 1: Update page header count**

In `templates/dashboard/patients.html`, replace:

```django
<div><h1 class="cf-page-title ui-page-title">Patients</h1><p class="cf-page-description">{{ patients|length }} patient records registered</p></div>
```

with:

```django
<div><h1 class="cf-page-title ui-page-title">Patients</h1><p class="cf-page-description">{{ page_obj.paginator.count }} patient records registered</p></div>
```

- [ ] **Step 2: Add pagination below the patient table**

Append this block after the closing `</section>` in `templates/dashboard/partials/patient_list.html`:

```django

{% if page_obj.paginator.num_pages > 1 %}
<nav class="flex flex-col gap-3 px-5 py-4 border-t border-[var(--cf-line)] sm:flex-row sm:items-center sm:justify-between">
  <p class="cf-muted">
    Showing {{ page_obj.start_index }}-{{ page_obj.end_index }} of {{ page_obj.paginator.count }}
  </p>
  <div class="flex flex-wrap justify-center gap-1 sm:justify-end">
    {% if page_obj.has_previous %}
      <a href="?page=1{% if query %}&q={{ query }}{% endif %}"
         class="cf-btn cf-btn-secondary px-3 py-1.5 text-sm"
         hx-get="?page=1{% if query %}&q={{ query }}{% endif %}"
         hx-target="#patient-list"
         hx-push-url="true"><i data-lucide="chevrons-left" class="h-4 w-4"></i>First</a>
      <a href="?page={{ page_obj.previous_page_number }}{% if query %}&q={{ query }}{% endif %}"
         class="cf-btn cf-btn-secondary px-3 py-1.5 text-sm"
         hx-get="?page={{ page_obj.previous_page_number }}{% if query %}&q={{ query }}{% endif %}"
         hx-target="#patient-list"
         hx-push-url="true"><i data-lucide="chevron-left" class="h-4 w-4"></i>Previous</a>
    {% endif %}
    {% for num in page_obj.paginator.page_range %}
      {% if page_obj.number == num %}
        <span class="cf-btn cf-btn-primary px-3 py-1.5 text-sm">{{ num }}</span>
      {% elif num > page_obj.number|add:'-3' and num < page_obj.number|add:'3' %}
         <a href="?page={{ num }}{% if query %}&q={{ query }}{% endif %}"
            class="cf-btn cf-btn-secondary px-3 py-1.5 text-sm"
            hx-get="?page={{ num }}{% if query %}&q={{ query }}{% endif %}"
            hx-target="#patient-list"
            hx-push-url="true">{{ num }}</a>
      {% endif %}
    {% endfor %}
    {% if page_obj.has_next %}
      <a href="?page={{ page_obj.next_page_number }}{% if query %}&q={{ query }}{% endif %}"
         class="cf-btn cf-btn-secondary px-3 py-1.5 text-sm"
         hx-get="?page={{ page_obj.next_page_number }}{% if query %}&q={{ query }}{% endif %}"
         hx-target="#patient-list"
         hx-push-url="true"><i data-lucide="chevron-right" class="h-4 w-4"></i>Next</a>
      <a href="?page={{ page_obj.paginator.num_pages }}{% if query %}&q={{ query }}{% endif %}"
         class="cf-btn cf-btn-secondary px-3 py-1.5 text-sm"
         hx-get="?page={{ page_obj.paginator.num_pages }}{% if query %}&q={{ query }}{% endif %}"
         hx-target="#patient-list"
         hx-push-url="true"><i data-lucide="chevrons-right" class="h-4 w-4"></i>Last</a>
    {% endif %}
  </div>
</nav>
{% endif %}
```

- [ ] **Step 3: Run template test**

Run: `.\env\Scripts\python -m pytest tests/test_design_system.py::test_patient_pagination_preserves_search_for_htmx -v`

Expected: PASS.

### Task 5: Verify Targeted Coverage

**Files:**
- No file changes.

- [ ] **Step 1: Run targeted dashboard tests**

Run: `.\env\Scripts\python -m pytest dashboard/tests.py::test_patients_list_orders_latest_created_first dashboard/tests.py::test_patients_page_paginates_ten_patients dashboard/tests.py::test_appointments_page_paginates_ten_appointments -v`

Expected: PASS.

- [ ] **Step 2: Run targeted design-system tests**

Run: `.\env\Scripts\python -m pytest tests/test_design_system.py::test_patient_empty_search_keeps_table_heading_and_columns_visible tests/test_design_system.py::test_patient_pagination_preserves_search_for_htmx tests/test_design_system.py::test_task_5_appointment_pagination_preserves_filters_for_htmx tests/test_design_system.py::test_patients_page_header_actions_and_search_toolbar_are_consistent tests/test_design_system.py::test_mobile_responsive_dashboard_shell_and_pagination_avoid_overlap_and_overflow -v`

Expected: PASS.

- [ ] **Step 3: Run Django system check**

Run: `.\env\Scripts\python manage.py check`

Expected: `System check identified no issues`.

### Task 6: Commit If Explicitly Requested

**Files:**
- Stage only intended changed files.

- [ ] **Step 1: Inspect worktree before any commit**

Run: `git status --short`

Expected: shows only intended changed files for this task, plus any unrelated pre-existing user changes that must not be staged.

- [ ] **Step 2: Inspect diff before any commit**

Run: `git diff -- dashboard/views.py dashboard/tests.py tests/test_design_system.py templates/dashboard/patients.html templates/dashboard/partials/patient_list.html docs/superpowers/specs/2026-06-03-patient-table-pagination-design.md docs/superpowers/plans/2026-06-03-patient-table-pagination-implementation-plan.md`

Expected: diff only contains the patient pagination implementation, tests, design spec, and implementation plan.

- [ ] **Step 3: Commit only if the user explicitly requested a commit**

Run only after an explicit commit request:

```bash
git add dashboard/views.py dashboard/tests.py tests/test_design_system.py templates/dashboard/patients.html templates/dashboard/partials/patient_list.html docs/superpowers/specs/2026-06-03-patient-table-pagination-design.md docs/superpowers/plans/2026-06-03-patient-table-pagination-implementation-plan.md
git commit -m "feat: paginate patients table"
```

Expected: a commit containing only the intended patient pagination files.

## Self-Review

- Spec coverage: The plan covers view pagination, Appointments-style table controls, search preservation, HTMX target/push URL behavior, clinic scoping preservation, and tests.
- Placeholder scan: No placeholder phrases, deferred implementation, or vague error-handling steps remain.
- Type consistency: The plan consistently uses Django `Paginator`, `page_obj`, `patients`, `query`, and `#patient-list`.

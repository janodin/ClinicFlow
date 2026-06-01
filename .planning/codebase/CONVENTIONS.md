# Coding Conventions

**Analysis Date:** 2026-05-31

## Naming Patterns

**Files:**
- `snake_case.py` for Python modules.
- `tests.py` or `test_*.py` for test files.

**Functions:**
- `snake_case()` for functions and methods.
- Example: `display_name(self)`, `find_or_create_for_booking(clinic, ...)`

**Variables:**
- `snake_case` for local variables and model fields.
- Example: `appointment_limit`, `trial_ends_at`.

**Types:**
- `PascalCase` for classes (Models, Forms, Views, etc.).
- Example: `ClinicGroup`, `TimeStampedModel`, `StaffAppointmentForm`.

## Code Style

**Formatting:**
- PEP 8 compliant.
- Two blank lines between classes and top-level functions.
- One blank line between methods within a class.

**Linting:**
- Not explicitly configured in the repository (no `.flake8` or `ruff.toml` found), but code follows strict PEP 8 patterns.

## Import Organization

**Order:**
1. Standard library imports (e.g., `from datetime import ...`).
2. Third-party imports (e.g., `import pytest`, `from django.db import models`).
3. Local app imports (e.g., `from clinics.models import Clinic`).

**Path Aliases:**
- Not detected. Standard relative and absolute imports used.

## Error Handling

**Patterns:**
- Use of `django.core.exceptions.ValidationError` for domain-level validation.
- `with pytest.raises(ValidationError):` used in tests to verify error states.

## Logging

**Framework:** Not explicitly configured in the observed files, likely uses standard Django logging.

## Comments

**When to Comment:**
- docstrings for classes to explain purpose.
- Example: `"""Clinic owner/staff login user. Patients remain guest records in V1."""` in `accounts/models.py`.

**JSDoc/TSDoc:**
- Not applicable (Python project).

## Function Design

**Size:** Generally small, single-responsibility methods.

**Parameters:** Descriptive names, often including type-hint-like clarity (though explicit type hints were not seen in all files).

**Return Values:** Explicit returns or standard Django model behavior.

## Module Design

**Exports:** Standard Python module behavior.

**Barrel Files:** Not used. Django app structure followed.

---

*Convention analysis: 2026-05-31*

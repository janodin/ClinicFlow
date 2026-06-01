# Testing Patterns

**Analysis Date:** 2026-05-31

## Test Framework

**Runner:**
- `pytest` 8.0+
- Config: `pytest.ini`

**Assertion Library:**
- Standard Python `assert` statements.

**Run Commands:**
```bash
pytest              # Run all tests
```

## Test File Organization

**Location:**
- Co-located in apps: `{app}/tests.py`.
- Centralized in `tests/` directory: `tests/*.py`.

**Naming:**
- `tests.py` (within apps).
- `test_*.py` (within `tests/` directory).

**Structure:**
```
[project-root]/
├── accounts/
│   └── tests.py
├── appointments/
│   └── tests.py
├── ...
└── tests/
    ├── conftest.py
    ├── test_domain.py
    └── test_flows.py
```

## Test Structure

**Suite Organization:**
```python
@pytest.mark.django_db
def test_behavior_name(fixture_name):
    # Setup
    # Action
    # Assertion
    assert condition
```

**Patterns:**
- `@pytest.mark.django_db` for any test requiring database access.
- Descriptive test function names starting with `test_`.

## Mocking

**Framework:** `unittest.mock` (standard library).

**Patterns:**
- Extensive use of database-backed fixtures instead of mocks for domain logic.
- Mocking likely used for external API calls (e.g., `n8n_api` if tested).

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def clinic_setup(db):
    # Creates User, ClinicGroup, Clinic, Membership, Service, and BusinessHours
    return clinic, service
```

**Location:**
- `tests/conftest.py`

## Coverage

**Requirements:** None enforced in `pytest.ini`.

**View Coverage:**
```bash
pytest --cov=.
```

## Test Types

**Unit Tests:**
- Model method testing and form validation (e.g., `test_patient_matching_is_scoped_to_clinic`).

**Integration Tests:**
- Slot generation and validation logic involving multiple models (`test_slot_generation_blocks_clinic_overlap`).

**E2E Tests:**
- Playwright listed in `requirements.txt`.
- Likely found in `tests/test_flows.py`.

## Common Patterns

**Async Testing:**
- Not observed.

**Error Testing:**
```python
with pytest.raises(ValidationError, match="expected error message"):
    function_that_fails()
```

---

*Testing analysis: 2026-05-31*

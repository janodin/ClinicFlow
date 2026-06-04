# Table Actions Design

## Context

The mobile responsiveness pass made appointment and patient table action columns sticky with `cf-sticky-action-col`. That kept row actions reachable during horizontal scrolling, but the pinned column creates a heavy visual slab inside dense operational tables.

## Approved Direction

Remove the sticky action-column treatment from dashboard tables and replace it with quiet, design-system action clusters.

## Design

- Keep the Actions column as a normal table column.
- Remove sticky positioning and shadow from action cells and headers.
- Keep actions inside `.cf-row-actions` so spacing remains reusable and consistent.
- Make the primary row action visually first and quiet: `View` uses the existing muted/view action treatment.
- Keep secondary actions as compact secondary pills.
- Keep destructive actions ruby via `.cf-btn-danger`.
- Preserve existing HTMX targets, Alpine modal triggers, URLs, labels, and form behavior.
- Preserve dense dashboard tables; do not convert tables to mobile cards.

## Affected Tables

- Appointments table: remove `cf-sticky-action-col` from the Actions header and row cells.
- Patients table and patient row partial: remove `cf-sticky-action-col` from the Actions header and row cells.
- CSS: remove or neutralize `.cf-sticky-action-col` if no longer used.
- Tests: update mobile design-system assertions so they verify quiet action clusters instead of sticky action columns.

## Verification

- Run targeted design-system tests for table actions.
- Run full design-system tests.
- Run `python manage.py check`.
- Run the relevant full test suite if targeted changes affect existing table tests.

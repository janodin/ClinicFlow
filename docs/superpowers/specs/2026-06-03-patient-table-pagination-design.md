# Patient Table Pagination Design

## Goal

Add pagination to the dashboard Patients table using the Appointments table as the reference pattern.

## Scope

Update the clinic dashboard Patients list only. Keep the existing patient search, add/edit modals, duplicate-check panel, table columns, row actions, and clinic scoping unchanged.

## Design

The Patients view will paginate `clinic.patients` after applying the optional `q` search filter. It will use the same page size as Appointments: 10 records per page. The context will pass `patients` as the current `page_obj` so the existing table loop keeps working, and it will also pass `page_obj` for pagination controls.

The Patients partial will add an Appointments-style pager below the table when there is more than one page. Controls will include First, Previous, nearby page numbers, Next, Last, and a `Showing start-end of total` summary. Links will preserve the current `q` search value and use HTMX with `hx-target="#patient-list"` and `hx-push-url="true"`.

## Tenant Safety

The queryset remains scoped through `clinic.patients`, so pagination never exposes records from another clinic. The change does not trust client-submitted clinic or patient ownership values.

## Testing

Add or update tests to confirm the Patients page paginates 10 records per page, preserves latest-created ordering, and includes HTMX pagination links that preserve the search query.

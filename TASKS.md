# TASKS.md - Clinic Booking SaaS V1

## Baseline Cleanup

- [ ] Move `D:/Downloads/AGENTS.md` into the project root as `AGENTS.md`
- [ ] Add `.gitignore` for Python, Django, SQLite, media, cache, Playwright, and local env files
- [ ] Add a project `README.md` with setup, run, test, and deployment notes
- [ ] Add a sample `.env` loading strategy or document how `.env.example` should be used
- [ ] Decide whether to keep or reset the current local SQLite demo/smoke data
- [ ] Add a demo data management command for repeatable local testing

## Authentication And Tenant Setup

- [ ] Improve signup validation and duplicate clinic slug handling
- [ ] Add first-run onboarding after signup
- [ ] Add clinic owner invite flow for staff
- [ ] Add password reset flow
- [ ] Add role-aware redirects after login
- [ ] Add tests for owner and staff access rules

## Permissions And Tenant Isolation

- [ ] Centralize tenant permission checks for dashboard views
- [ ] Restrict staff from tenant billing, user management, and owner-only settings
- [ ] Add cross-clinic isolation tests for every major model/view
- [ ] Add graceful forbidden/error pages for permission failures

## Dashboard Polish

- [ ] Improve responsive sidebar behavior for mobile/tablet
- [ ] Add mobile dashboard navigation
- [ ] Add empty states for dashboard, appointments, patients, and services
- [ ] Add loading/disabled states for forms and buttons
- [ ] Improve global search behavior
- [ ] Add consistent success/error toast styling

## Appointment Management

- [ ] Add better staff-created appointment form with date/time picker
- [ ] Add appointment edit flow
- [ ] Add appointment cancellation reason
- [ ] Add reschedule flow with slot validation
- [ ] Add appointment detail modal instead of full-page detail only
- [ ] Add appointment filters for date range, service, source, and payment state
- [ ] Add appointment export CSV
- [ ] Add tests for status transitions and rescheduling

## Calendar

- [ ] Add drag-and-drop rescheduling persistence
- [ ] Add server-side validation for calendar drag/drop changes
- [ ] Add appointment detail modal from calendar click
- [ ] Add color legend for statuses
- [ ] Add service filters on calendar
- [ ] Add tests for calendar event JSON and reschedule endpoint

## Patients

- [ ] Add patient edit flow
- [ ] Add patient duplicate merge flow
- [ ] Add patient appointment history improvements
- [ ] Add patient notes display and editing
- [ ] Add phone normalization display improvements
- [ ] Add tests for patient matching and duplicate handling


## Services

- [ ] Add service edit flow
- [ ] Add service delete/archive behavior
- [ ] Add service-specific duration validation
- [ ] Add optional service price display controls
- [ ] Add tests for service assignment and duration fallback

## Scheduling And Availability

- [ ] Add clinic business hours UI
- [ ] Add break time editing UI
- [ ] Add unavailable dates UI
- [ ] Add holiday/unavailable day support
- [ ] Add slot preview tool for staff
- [ ] Add tests for business hours, breaks, and unavailable dates

## Public Booking Flow

- [ ] Improve multi-step booking UX
- [ ] Add confirmation review step before final submit
- [ ] Add better no-slots-available state
- [ ] Add clinic branding/logo on booking page
- [ ] Add optional reason-for-visit field display setting
- [ ] Add booking success page with appointment reference/code
- [ ] Add Playwright test for full guest booking flow

## Widget And Embed

- [ ] Improve embedded widget booking UX
- [ ] Add copy buttons for iframe/script snippets
- [ ] Add widget accent color live preview
- [ ] Add widget minimized/floating launcher mode
- [ ] Add structured guided chat booking state machine
- [ ] Add FAQ answer display in chat mode
- [ ] Add widget source tracking tests

## Notifications

- [ ] Convert console email setup to documented SMTP production setup
- [ ] Add HTML email templates
- [ ] Add clinic/staff notification recipient settings
- [ ] Add reminder timing setting per clinic
- [ ] Add notification retry behavior
- [ ] Add notification log UI
- [ ] Add tests for confirmation, staff notification, reminder eligibility, and failure handling

## Billing And SaaS Plan Limits

- [ ] Keep billing manual in V1 but improve billing page clarity
- [ ] Enforce manual plan appointment/staff limits if needed
- [ ] Add super-admin fields for plan/status changes
- [ ] Add trial status display
- [ ] Add tests for plan/status display

## Deployment Readiness

- [ ] Add production settings module or environment-based production config
- [ ] Configure PostgreSQL setup instructions
- [ ] Add Gunicorn command/config example
- [ ] Add Nginx config example
- [ ] Add static/media deployment instructions
- [ ] Add cron documentation for reminders
- [ ] Add health check endpoint
- [ ] Add basic logging configuration

## QA And Testing

- [ ] Expand unit tests for models and services
- [ ] Expand integration tests for dashboard flows
- [ ] Add Playwright tests for core UI flows
- [ ] Add fixture/demo data for tests
- [ ] Add accessibility checks for major forms
- [ ] Add responsive screenshots for dashboard, public booking, and widget
- [ ] Add CI-ready test command documentation

# Production Security Hardening Design

## Context

This Django clinic booking SaaS is preparing for production. Three read-only security deep dives reviewed authentication and tenant isolation, Django deployment security, and public booking/widget security. The highest-risk findings were fail-open Messenger/n8n webhooks, unsafe production defaults, public token exposure, weak guest booking validation, patient identity mutation from unauthenticated bookings, race-prone appointment creation, and direct POST permission bypasses.

Messenger/n8n automation will be kept and hardened rather than disabled or removed.

## Goals

- Fail closed for all trusted integration endpoints unless required secrets or signatures are valid.
- Make production configuration safe by default and explicit about required secrets, hosts, HTTPS, cookies, and proxy trust.
- Preserve guest booking without login while preventing corrupt patient records, appointment source spoofing, stale slot use, and double-booking races.
- Preserve clinic data isolation and add missing permission checks to staff/dashboard mutation routes.
- Add targeted tests for the identified exploit paths and run Django production checks.

## Non-Goals

- No patient portal, medical records, prescriptions, payments, marketplace booking, or new AI capability.
- No React, Next.js, separate frontend, or major UI redesign.
- No broad rewrite of appointment scheduling beyond the minimum needed to protect booking integrity.

## Security Boundaries

- Production settings boundary: environment values control production mode, required secrets, allowed hosts, CSRF trusted origins, HTTPS, secure cookies, HSTS, and proxy trust.
- Trusted webhook boundary: n8n/AI tool endpoints require a configured shared secret; the legacy Messenger webhook requires a valid Meta HMAC signature.
- Public booking boundary: unauthenticated users can book, but all submitted identity, service, time, and source data is validated server-side.
- Clinic data boundary: dashboard mutations use current clinic membership and owner/settings permissions consistently.

## Planned Changes

- Replace unsafe settings fallbacks with development-only fallbacks and production checks for `SECRET_KEY`, `ALLOWED_HOSTS`, secure cookies, HTTPS redirect, HSTS, and integration secrets.
- Make `_verify_n8n_secret()` fail closed and use constant-time comparison.
- Verify `X-Hub-Signature-256` for legacy Messenger POSTs using `MESSENGER_APP_SECRET` before processing any payload.
- Avoid leaking Facebook page access tokens to unauthenticated callers; if the existing n8n send-message workflow still needs the token, return it only after successful shared-secret authentication.
- Add server-side guest booking validation for name, phone, email, service, and start time.
- Stop unauthenticated guest bookings from overwriting existing patient name, email, or notes based only on phone matching.
- Protect appointment creation with an atomic transaction that locks the clinic row, rechecks slot availability inside the transaction, and creates at most one overlapping appointment per clinic.
- Derive public appointment source from the route/context instead of trusting hidden form values.
- Add server-side validation for widget accent color and render script-bound values safely.
- Apply owner/settings permission checks to FAQ mutation endpoints that currently bypass the owner-only settings page.
- Update deployment documentation and examples so production operators have explicit security gates.

## Error Handling

- Bad n8n shared secrets return `401`.
- Missing or invalid Messenger signatures return `403`.
- Invalid booking input returns a user-safe validation error without creating patients or appointments.
- Stale or contested slots return a conflict response without leaking other appointment details.
- Production misconfiguration raises explicit Django check errors or startup errors before serving traffic.

## Testing

- Webhook tests cover missing, invalid, and valid n8n secrets.
- Messenger tests cover missing, invalid, and valid Meta signatures.
- Booking tests cover missing or weak patient identity, service/time tampering, source spoofing, and stale slot handling.
- Patient tests confirm guest bookings by known phone do not mutate existing demographics.
- Permission tests confirm non-owner staff cannot mutate assistant FAQ settings directly.
- Widget settings tests confirm invalid colors are rejected and rendered values are escaped.
- Appointment integrity tests confirm overlapping booking attempts cannot both succeed.
- Verification includes `python manage.py check`, migration checks when models change, and `python manage.py check --deploy` for production warnings.

## Risks and Tradeoffs

- Secure-by-default settings may require local `.env` updates for developers and webhook tests.
- PostgreSQL exclusion constraints are stronger long-term, but this pass will use clinic-row locking to minimize schema risk and keep local tests practical.
- Keeping Messenger/n8n increases attack surface, so fail-closed secrets, signature verification, and token minimization are mandatory.

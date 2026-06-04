# CRITICAL RULES - MUST FOLLOW

## RESPONSES

- Keep responses concise and to the point - unless the user asks otherwise

## PROJECT CONTEXT

- This project is a Clinic Management and Appointment Booking SaaS
- Tech stack: Django, PostgreSQL, Django templates, Tailwind CSS, HTMX, Alpine.js, FullCalendar, pytest, Playwright
- V1 is appointment-first and multi-tenant
- One tenant represents one clinic/location for now, but the database uses `ClinicGroup` + `Clinic` for future multi-branch support
- Patients book as guests without login/password in V1
- Do not add patient portal, medical records, prescriptions, inventory, online payments, marketplace booking, or real AI/Messenger automation unless explicitly requested

## PLANNING MODE

- Ask clarifying questions when requirements, scope, design, or acceptance criteria are ambiguous
- Never assume design, tech stack or features
- Use the existing plan and current Django codebase as source of truth
- Do not plan Next.js, Supabase, Drizzle, or a separate frontend unless the user explicitly changes the stack
- Use deep-dive sub-agents for major, multi-file, security-sensitive, UI-wide, complex debugging, or planning/review work

## CHANGE / EDIT MODE

- Implement changes directly unless the user explicitly asks for planning only
- Keep changes aligned with the existing Django app structure:
  - `accounts`
  - `clinics`
  - `doctors`
  - `services`
  - `patients`
  - `scheduling`
  - `appointments`
  - `notifications`
  - `dashboard`
  - `widget`
- Use sub-agents deliberately for delegation, parallel research, major implementation, and review loops when they reduce risk or improve coverage
- Keep clinic-owned data scoped by `Clinic` and/or `ClinicGroup`
- Never expose data across clinics
- Preserve guest booking, patient phone matching, appointment slot validation, and double-booking prevention
- For major, multi-file, security-sensitive, or UI-wide changes, use sub-agents for implementation/review loops instead of relying on one pass
- For small single-file edits, still self-review and run the smallest meaningful verification command
- When removing or changing features/code, always remove the corresponding code, files, templates, URLs, tests, and imports if they are no longer needed — do not leave commented-out code, dead imports, or unused files

## ENGINEERING QUALITY

- Prefer the smallest correct change that preserves current product behavior
- Use test-driven development for behavior changes, bug fixes, validation logic, security-sensitive paths, booking flows, tenant scoping, and regression fixes
- For UI-only/template-only changes, update or add design-system/template tests when there is meaningful drift risk
- Run targeted tests for the files or behavior changed before running broader suites
- Before claiming work is complete, always run fresh verification and report the actual command results
- Never silence, skip, or weaken tests to make a change pass; fix the root cause or explain the blocker
- When a test fails or behavior is unexpected, use systematic debugging: reproduce, identify root cause, compare working patterns, then fix
- Preserve existing public APIs, URLs, form field names, DOM IDs, HTMX targets, Alpine state hooks, and FullCalendar hooks unless the change explicitly requires replacing them
- Do not add compatibility code unless there is a concrete need such as persisted data, shipped behavior, external consumers, or an explicit user requirement
- Keep files focused and avoid broad refactors unless they directly support the requested change

## SECURITY / TENANT SAFETY

- Treat every public widget, HTMX, Messenger, n8n, webhook, and form input as untrusted
- Never trust client-submitted clinic, patient, service, appointment, status, price, source, or ownership values without server-side validation
- Always scope clinic-owned objects through the active clinic or an explicitly resolved public clinic slug
- All dashboard/staff views and actions must require authentication, clinic membership/authorization, and clinic-scoped object lookup; never trust URL IDs alone
- Use clinic-scoped querysets such as `clinic.appointments`, `clinic.patients`, and `clinic.services` for dashboard object lookups
- Validate cross-object ownership before saving: `Patient`, `Service`, `Appointment`, scheduling settings, FAQs, widget settings, and Messenger settings must belong to the same clinic
- Preserve guest booking safeguards: normalized phone matching, slot regeneration before booking, appointment overlap checks, clinic row locking where used, and cancelled-slot behavior
- Webhook endpoints must verify signatures/secrets where applicable, reject unsigned or invalid requests, avoid logging payload secrets, and scope resulting writes to the resolved clinic
- Do not expose secrets, access tokens, webhook secrets, page tokens, API keys, credentials, `.env` values, or sensitive settings in templates, logs, tests, screenshots, or commits
- Do not add payment collection, Stripe payment APIs, patient portals, medical records, prescriptions, inventory, marketplace booking, or real AI/Messenger automation unless explicitly requested
- For destructive actions, preserve POST-only behavior, CSRF protection, permission checks, and clinic scoping
- For exported data, search, and dashboards, ensure results are limited to the current clinic/clinic group

## DEVELOPMENT ENVIRONMENT

- Project uses a Python virtual environment (`env/`) for dependency isolation
- Activate the virtual environment before running commands:
  - Windows: `.\env\Scripts\activate`
- For local setup only, copy `.env.example` to `.env` if missing; never commit `.env` or expose its values
- Start server: `python manage.py runserver`

## DATABASE SCHEMA CHANGES

- This is a Django project
- Whenever you change Django models, ALWAYS run:
  - `python manage.py makemigrations`
  - `python manage.py migrate` when using a local development database
  - `python manage.py check`
- If migration commands cannot be run, report the blocker and do not claim the schema change is verified
- NEVER run Drizzle commands
- NEVER run `drizzle push`

## GIT / WORKTREE HYGIENE

- Always work directly on the `main` branch; do not create or use git worktrees
- The worktree may contain user or agent changes; never revert or overwrite changes you did not make unless explicitly asked
- Before committing, inspect `git status`, `git diff`, and recent commits; stage only intended files
- Do not commit local databases, generated brainstorm artifacts, debug screenshots, temporary output, secrets, or unrelated files
- Common files to exclude from commits unless explicitly requested: `db.sqlite3`, `.superpowers/`, `tmp_visual_checks/`, debug images, `test_output.txt`, and ad-hoc deploy/debug scripts
- Do not amend, force-push, reset hard, or run destructive git commands unless explicitly requested

## UI DESIGN

- Use `DESIGN.md` as the source of truth for UI design tokens, component patterns, layout rules, and visual guardrails
- The active visual direction is the Neon Aqua Clinical system: white/ice-cyan surfaces, deep teal ink, electric aqua CTAs, pill buttons, compact radii, subtle teal shadows, thin display typography, tabular numerics, and selective cyan glow mesh accents
- Before creating, changing, or reviewing UI, read `DESIGN.md` and follow the Neon Aqua Clinical tokens and component guidance
- Implement the design through the existing Django template stack and `static/css/clinicflow.css`; keep `cf-*` classes as the canonical reusable UI layer
- When adding new designs, components, or patterns, reference existing `cf-*` classes and current templates before introducing new classes
- Operational dashboard screens must stay appointment-first, dense, table-first, and optimized for clinic staff workflows; do not turn them into marketing pages
- Public booking, widget, auth, and confirmation surfaces may use the aqua glow mesh where text contrast remains accessible
- Use Inter as the practical Sohne substitute; use weight 300 for display/page titles and tabular numerics for KPIs, times, prices, durations, and counts
- Primary actions should use electric aqua and pill geometry; secondary actions should remain clear, quiet, and accessible
- Status badges must keep appointment meaning distinct: pending/booked, confirmed, completed, cancelled, and no-show cannot collapse into one generic aqua treatment
- No unreadable text: every dropdown, menu, select option, disabled state, toast, badge, modal, table cell, widget state, and gradient surface must meet WCAG AA contrast
- Preserve left sidebar navigation, compact KPI cards, status badges, rounded cards/modals, table-first operational screens, focused public booking form, and floating embeddable widget behavior
- Use Django templates + Tailwind CSS
- Use HTMX for dynamic server-rendered interactions
- Use Alpine.js only for small UI behavior
- Do not introduce React, Next.js, or a separate frontend in V1 unless explicitly requested

## SUPERPOWERS / SKILLS

Superpowers are specialized skill files that inject domain-specific instructions and workflows into the agent. They are installed under `~/.config/opencode/skills/` and `~/.claude/skills/`.

### How to Use Them

You invoke a skill by name in your prompt. Examples:

- **Before starting creative work**: "Use the brainstorming skill to think through this feature"
- **Before writing code**: "Use the test-driven-development skill for this bugfix"
- **Before merging**: "Use the requesting-code-review skill to review this PR"
- **When stuck on a bug**: "Use the systematic-debugging skill to investigate this"
- **For UI work**: "Use the frontend-design skill to build this component"
- **For planning a milestone**: "Use the gsd-plan-phase skill to plan this feature"

### Key Skills Available

| Skill | When to Use |
|-------|-------------|
| `brainstorming` | Before any creative work or new features |
| `writing-plans` | Before multi-step implementation tasks |
| `test-driven-development` | Before writing implementation code |
| `systematic-debugging` | When encountering bugs or test failures |
| `frontend-design` | For building/reviewing UI components |
| `verification-before-completion` | Before claiming work is done |
| `gsd-plan-phase` | For planning a development phase |
| `gsd-execute-phase` | For executing a planned phase |
| `gsd-code-review` | For reviewing code before merge |
| `gsd-debug` | For complex multi-cycle debugging |

### Full GSD Suite

The `gsd-*` skills provide a complete project management workflow: `gsd-new-project`, `gsd-new-milestone`, `gsd-spec-phase`, `gsd-discuss-phase`, `gsd-plan-phase`, `gsd-execute-phase`, `gsd-verify-work`, `gsd-audit-fix`, `gsd-ship`, and many more.

### Important Notes

- **Skills override default behavior** but your explicit instructions always take priority
- **Process skills first** (brainstorming, debugging), then implementation skills (frontend-design)
- Some skills are **rigid** (TDD, debugging) and must be followed exactly; others are **flexible**
- You can say things like: "Use brainstorming, then frontend-design to build a patient dashboard"

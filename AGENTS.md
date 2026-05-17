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

- Always ask clarifying questions
- Never assume design, tech stack or features
- Use the existing plan and current Django codebase as source of truth
- Do not plan Next.js, Supabase, Drizzle, or a separate frontend unless the user explicitly changes the stack
- Always use deep-dive sub-agents to assist with fixing and debugging issues
- Always use deep-dive sub-agents to review different aspects of your plan

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
- Always use sub-agents for delegation and parallel agents
- Keep clinic-owned data scoped by `Clinic` and/or `ClinicGroup`
- Never expose data across clinics
- Preserve guest booking, patient phone matching, appointment slot validation, and double-booking prevention
- When removing or changing features/code, always remove the corresponding code, files, templates, URLs, tests, and imports if they are no longer needed — do not leave commented-out code, dead imports, or unused files

## DEVELOPMENT ENVIRONMENT

- Project uses a Python virtual environment (`env/`) for dependency isolation
- Activate the virtual environment before running commands:
  - Windows: `.\env\Scripts\activate`
- Copy `.env.example` to `.env` and configure for local development
- Start server: `python manage.py runserver`

## DATABASE SCHEMA CHANGES

- This is a Django project
- Whenever you change Django models, ALWAYS run:
  - `python manage.py makemigrations`
  - `python manage.py migrate`
  - `python manage.py check`
- NEVER run Drizzle commands
- NEVER run `drizzle push`

## UI DESIGN

- Use `DESIGN.md` as the source of truth for UI design tokens, component patterns, layout rules, and product-specific UI guardrails
- Before creating, changing, or reviewing UI, read `DESIGN.md` and follow its Google Stitch design system guidance
- Always follow the current Clinic Booking SaaS UI direction when creating or reviewing components/pages
- When adding new designs, components, or patterns, always reference existing codebase patterns for consistency
- Design style:
  - clean teal/white SaaS dashboard
  - left sidebar navigation
  - compact KPI cards
  - status badges
  - rounded cards/modals
  - table-first operational screens
  - focused public booking form
  - floating embeddable widget
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

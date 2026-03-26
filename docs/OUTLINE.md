# Real Estate CRM Outline and Build Status

Last updated: 2026-03-25

## Purpose
This document tracks what is implemented in the app today and what remains.

## Current Status Summary
- Completed: Auth, org/team workspace, contacts, lead forms, pipelines, tasks, properties, open houses, transactions, reports, notifications, global search, calendar, base theme.
- In progress: External provider implementations (MLS/Zillow/Calendar/Voice/E-sign).
- Not started: MLS/Zillow integration, document storage/e-sign, brokerage compliance module, commission split engine, client portal.

## Module Status

### 1) Platform and Workspace
- [x] User auth (register/login/logout/password reset/change)
- [x] Organization model (individual/team/brokerage)
- [x] Membership roles (owner/admin/member/viewer)
- [x] Team settings and membership management UI
- [x] Dashboard shell, sidebar nav, Bootstrap + Bootstrap Icons, theme.css/theme.js

### 2) CRM Core (Contacts)
- [x] Rich contact profile (identity, preferences, buyer/seller fields, referral fields)
- [x] Contact notes/activity timeline (call/text/email/meeting/open house/system)
- [x] Contact filters/search/list/detail/create/edit
- [x] Contact tags and tag assignment
- [x] Contact soft delete
- [x] Contact CSV import with header mapping + duplicate handling
- [x] Contact CSV export
- [x] Public agent-page inquiry capture (creates/updates lead contact, logs inquiry note, and creates follow-up task)

### 3) Lead Capture
- [x] Public lead capture forms with per-form field configuration
- [x] Form submissions saved and linked to contacts
- [x] Lead source attribution and assignee routing
- [x] Lead form management UI (create/edit/list/detail/toggle/delete)
- [x] New lead notifications for assigned agent
- [x] Auto-create lead pipeline deal on form conversion

### 4) Pipeline Management
- [x] Default pipelines for lead/buyer/seller/recruiting
- [x] Stage definitions with probability/expected days/color
- [x] Deal CRUD
- [x] Kanban board by pipeline
- [x] Stage movement + immutable stage history
- [x] Won/lost handling
- [x] Stage-level required tasks/forms/automation rules (v1 requirements + enforcement + auto-task provisioning)

### 5) Tasks and Follow-up
- [x] Task CRUD and tabs (today/overdue/upcoming/completed)
- [x] Task filters (search/type/assignee)
- [x] Complete/snooze/delete actions
- [x] Recurring tasks with next-task generation
- [x] Task templates model
- [x] Follow-up center (no-next-step, going-cold, birthdays, anniversaries)
- [x] Reminder generation (birthday/home anniversary)

### 6) Communications
- [x] Communication logging on contacts (call/text/email/note)
- [x] Message templates (email/sms/call script) with merge preview
- [x] Outbound email send from contact detail (SMTP/backend configured in Django settings)
- [x] SMS send from contact detail via provider integration (console/twilio backend)
- [x] Drip/campaign sending engine v1 (campaigns, steps, enrollments, send logs, runner command)
- [x] One-time mass outreach v1 (email/SMS audience preview, consent checkpoint, guardrail send limit, delivery logs)
- [x] Broadcast scheduling + approval baseline (schedule time, pending/approved states, second-approver guardrail, scheduled runner command)
- [x] Advanced segmentation baseline for broadcasts (tags, geography, inactivity window, and reusable saved segments)
- [x] Broadcast compliance controls baseline (quiet-hours skip policy + legal footer enforcement + explicit suppression logging)
- [x] Broadcast analytics dashboard baseline (delivery trend, status totals, top templates, top segments)

### 7) Properties, Open Houses, Transactions
- [x] Property records with listing details and photos
- [x] Open house scheduling and staff detail pages
- [x] Public open house sign-in endpoint via token
- [x] Visitor conversion to contact
- [x] Auto-create lead deal + follow-up task on open house conversion
- [x] Open house visitor export CSV
- [x] Transaction CRUD with key dates and milestones
- [x] Transaction checklist seeding + progress tracking
- [x] Transaction notes and deadline helpers
- [x] Document center v1 (transaction/contact uploads by category + required-document checklist and missing flags)

### 8) Reporting and Analytics
- [x] Reports: overview, contacts, pipeline, tasks, transactions/GCI
- [x] Dashboard cards and operational widgets
- [x] Pipeline value summaries and activity feed
- [x] Forecasting depth and team scorecards (weighted forecast, close-window forecast buckets, per-agent scorecards)

### 9) Notifications and Search
- [x] Notification center (read/unread)
- [x] Signal-based notifications for task due/overdue and contact assignment
- [x] Global search across contacts/properties/transactions/tasks

### 9.5) Automation Engine
- [x] Automation rule model (org-scoped triggers/conditions/actions)
- [x] Automation run log model
- [x] Trigger execution engine with actions: assign owner, create task, change stage, create note, notify
- [x] Trigger hook: lead created (lead forms + open house conversion)
- [x] Trigger hook: deal stage changed
- [x] Scheduled trigger runner command for overdue tasks (`manage.py run_automation_triggers`)
- [x] Rule management UI (list/create/edit/delete)
- [x] Basic JSON shape validation for conditions/actions
- [x] Strict schema guardrails (allowed keys, required fields, trigger-safe action constraints)
- [x] Rich condition builder (multi-branch logic via nested `all`/`any`/`not` JSON)

### 10) Permissions and Compliance
- [x] Basic org data scoping via `for_org`
- [x] Basic membership roles
- [x] Enforced role checks on create/edit/delete endpoints (viewer read-only; member/admin/owner write; admin+ for workspace automation/campaign/form tools)
- [x] Per-role capabilities matrix and UI surfacing (including role-based nav/settings visibility)
- [x] Audit/compliance workflows and retention controls (audit events, compliance policy, retention purge command, compliance dashboards)

### 11) Integrations
- [x] Integration groundwork baseline (connection models, calendar sync abstraction, listing provider adapters/scaffolding)
- [ ] MLS/IDX integration
- [ ] Zillow API integration (requested, pending)
- [x] Google Calendar outbound sync baseline (OAuth, token refresh, push events)
- [x] Outlook Calendar outbound sync baseline (OAuth, token refresh, push events)
- [x] Calendar pull sync baseline with mapped-event conflict detection
- [ ] Voice/call provider integration
- [ ] E-sign/document storage integration

## Completed in this update (2026-03-24)
- [x] Fixed contacts tag-management runtime issue by adding missing org resolver helper.
- [x] Fixed tag usage count query to use the correct M2M relation.
- [x] Fixed transaction list search logic to keep active tab/status scope and use a unified query filter.
- [x] Fixed lead form notification string bug that could break execution.
- [x] Added auto lead-deal creation for lead form conversions.
- [x] Added auto lead-deal creation and auto follow-up task creation when converting open house visitors.
- [x] Added Automation Engine v1 foundation (rules, run logs, execution engine, trigger hooks, scheduled overdue runner).
- [x] Added Automation Rules in-app UI and rule JSON validation.
- [x] Added strict automation schema guardrails (conditions/actions validation + safer action constraints).
- [x] Added outbound email sending from contact communication panel with logging and failure notes.
- [x] Added SMS sending from contact communication panel with provider adapter and failure notes.
- [x] Added drip campaign module (campaign UI, step management, enrollment tracking, and send runner command).
- [x] Added centralized role guard utilities and applied them to mutating endpoints across core modules.
- [x] Added centralized per-role capability matrix, surfaced it in Team Settings, and gated sidebar/settings UI by capabilities.
- [x] Added multi-branch automation conditions support (`all` / `any` / `not`) with recursive validation and engine evaluation.
- [x] Added pipeline stage-level requirements v1 (required tasks/forms/automation rules, optional enforcement on stage entry, and requirement checklist on deal detail).
- [x] Added compliance module v1: audit event model, retention policy, purge command, compliance dashboard, and compliance reporting tab.
- [x] Added audit logging hooks for critical actions (team role/member changes, deal moves/deletes, and key template/automation/form/task/transaction/property/open-house deletions).
- [x] Expanded pipeline reporting with weighted forecasting, expected-close forecast windows, and team scorecards.
- [x] Added compliance export hardening baseline: scoped audit CSV exports, checksum header, and export log trail.
- [x] Added retention monitoring baseline: dashboard health signals and `manage.py monitor_retention` command for ops alerting.
- [x] Added non-JSON visual automation builder UX in rule editor (condition/action row builder with JSON sync on save).
- [x] Added signed compliance ZIP package exports with persisted artifacts and verification tooling (`verify_compliance_exports` command).
- [x] Added PDF bundle option for signed compliance exports (`summary.pdf` in package + manifest hash verification).
- [x] Added Document Center v1 for transactions and contacts (category-based uploads, required-document checklist, and missing-document flags).
- [x] Added Integration Groundwork baseline (new `integrations` app with provider connection models, calendar adapter interface, MLS/Zillow listing adapter interface, integration wiring check command, and Integration Settings UI scaffold).
- [x] Added initial calendar push sync job (`manage.py sync_calendar_events`) with persisted event mapping for tasks, open houses, and closings.
- [x] Added OAuth connection scaffolding for Google/Outlook calendar providers (start/callback flow with code capture).
- [x] Added Google OAuth token exchange/refresh plumbing and live Google Calendar adapter calls for list/upsert/delete.
- [x] Added Outlook OAuth token exchange/refresh plumbing and Microsoft Graph Calendar adapter calls for list/upsert/delete.
- [x] Added calendar pull sync baseline (`manage.py pull_calendar_updates`) with mapped-event conflict detection.
- [x] Added listing sync execution baseline (`manage.py sync_listing_data`) with provider fetch, listing state updates, optional property field merge, and optional photo import.
- [x] Added integration sync run observability + controls (`IntegrationSyncRun` log model, retries, max-failure threshold, and fail-on-error support across sync commands).
- [x] Added integration sync alert routing to in-app notifications for owner/admin users on failed/high-error runs.
- [x] Added exponential backoff retry controls across integration sync commands (`--retry-backoff-seconds`, `--retry-backoff-factor`, `--retry-backoff-max-seconds`).
- [x] Added alert escalation tiers for integration sync health (warning vs critical based on failure ratio and consecutive failed runs).
- [x] Added shared-database schema isolation support (`DB_SCHEMA`) and `manage.py ensure_db_schema` helper command for safer multi-site deployments.
- [x] Added startup/system-check warning for unsafe hosted config when `DB_SCHEMA=public` (`organizations.W001`).
- [x] Added deploy gate command for schema isolation (`manage.py db_isolation_gate [--json] [--fail-on-warning]`).
- [x] Added active workspace switching (session-backed `active_org_id`) with sidebar selector and unified org resolution across core modules.
- [x] Hardened workspace switch redirect handling to block unsafe external `next` URLs.
- [x] Added dedicated SaaS Ops Center (`/settings/ops/`) with one-click full health check reporting and matching `manage.py ops_health_check` command.
- [x] Added public agent page foundation (`/public/agents/<slug>/`) with agent/broker branding profile and MLS-ID listing cards managed from Settings.
- [x] Added public agent-page lead capture form (visitor inquiry -> contact + system note + agent follow-up task).
- [x] Added manual listing fallback editor for public listing cards when MLS hydration is unavailable.

## Next Build Queue (recommended order)
1. Calendar and listing provider implementations
- Bi-directional calendar hardening (remote -> local mutation rules, conflict resolution UX)
- Background sync hardening (retries, monitoring, idempotency checks)
- MLS/IDX and Zillow provider implementations using live credentials

2. External integrations
- MLS/IDX integration
- Zillow API integration
- Voice/call provider integration
- E-sign/document storage integration

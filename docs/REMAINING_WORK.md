# Remaining Work

Last updated: 2026-03-25
Source: `docs/OUTLINE.md`

Integration groundwork baseline is complete (`integrations` app, provider connection records, adapter interfaces, settings scaffold).
Initial sync orchestration is in place (`manage.py sync_calendar_events`) with event mapping storage.
Listing sync orchestration is in place (`manage.py sync_listing_data`) with listing-state tracking and optional property/photo updates.
Sync observability baseline is in place (`IntegrationSyncRun`, retries + exponential backoff, max-failure controls, fail-on-error switches, in-app alerts for failed/high-error runs).
Shared database schema isolation baseline is in place (`DB_SCHEMA` + `manage.py ensure_db_schema`).
Shared database isolation deploy gate is in place (`manage.py db_isolation_gate` with optional `--fail-on-warning`).
Active workspace selection baseline is in place (session-backed org switcher + unified resolver wiring across core modules).
Dedicated Ops Center baseline is in place (in-app full health check runner + `manage.py ops_health_check` automation hook).
Public agent page baseline is in place (agent/broker profile sections and MLS-ID listing cards with close-out controls).
MLS lookup adapter now supports MLS Grid-style OData payload parsing (`value[]`, `Media`, `MlgCanView`, `MlgCanUse`) with public-display safety guards.
Public agent-page inquiry capture is in place (visitor inquiry -> contact/note/task in CRM).
Manual listing fallback editor is in place for public cards when MLS auto-fill does not return data.
One-time mass outreach baseline is in place (broadcast UI + recipient preview + consent confirmation + delivery logs).
Broadcast scheduling and approval baseline is in place (pending approval queue + `run_scheduled_broadcasts` command processing due approved sends).
Advanced segmentation baseline is in place for broadcasts (tags, geography, inactivity windows, saved audience segments).
Broadcast compliance controls baseline is in place (quiet-hours suppression and legal footer enforcement).
Broadcast analytics dashboard baseline is in place (delivery totals, trend view, top templates/segments).

## Not Yet Completed

### Integrations
- MLS/IDX provider hardening (credentials, robust schema mapping, rate-limit/error policy)
- Zillow API integration hardening (beyond MLS photo-template fallback) https://media.mlspin.com/photo.aspx?mls={mls}&n={num}&w=1024&h=768
- Calendar bi-directional sync hardening (create/update local objects from remote events, conflict resolution UX)
- Voice/call provider integration
- E-sign/document storage integration

### Communications
- Advanced engagement analytics (opens/clicks/replies and campaign-level attribution)

## Recommended Next Build Order
1. Calendar and listing provider implementations
- Background sync hardening (remote->local mutation rules, reconciliation workflows, and monitoring dashboards)
- MLS/IDX and Zillow provider hardening using live credentials

2. Provider rollouts
- Voice/call provider integration
- E-sign/document storage integration

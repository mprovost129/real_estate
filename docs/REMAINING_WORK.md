# Remaining Work

Last updated: 2026-03-25
Source: `docs/OUTLINE.md`

Integration groundwork baseline is complete (`integrations` app, provider connection records, adapter interfaces, settings scaffold).
Initial sync orchestration is in place (`manage.py sync_calendar_events`) with event mapping storage.
Listing sync orchestration is in place (`manage.py sync_listing_data`) with listing-state tracking and optional property/photo updates.
Sync observability baseline is in place (`IntegrationSyncRun`, retries + exponential backoff, max-failure controls, fail-on-error switches, in-app alerts for failed/high-error runs).

## Not Yet Completed

### Integrations
- MLS/IDX provider hardening (credentials, robust schema mapping, rate-limit/error policy)
- Zillow API integration hardening (beyond MLS photo-template fallback) https://media.mlspin.com/photo.aspx?mls={mls}&n={num}&w=1024&h=768
- Calendar bi-directional sync hardening (create/update local objects from remote events, conflict resolution UX)
- Voice/call provider integration
- E-sign/document storage integration

## Recommended Next Build Order
1. Calendar and listing provider implementations
- Background sync hardening (alert routing escalation policies and remote->local mutation rules)
- MLS/IDX and Zillow provider hardening using live credentials

2. Provider rollouts
- Voice/call provider integration
- E-sign/document storage integration

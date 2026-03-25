# Remaining Work

Last updated: 2026-03-24
Source: `docs/OUTLINE.md`

Integration groundwork baseline is complete (`integrations` app, provider connection records, adapter interfaces, settings scaffold).
Initial sync orchestration is in place (`manage.py sync_calendar_events`) with event mapping storage.

## Not Yet Completed

### Integrations
- MLS/IDX integration
- Zillow API integration (requested, pending access) https://media.mlspin.com/photo.aspx?mls={mls}&n={num}&w=1024&h=768
- Calendar pull sync + conflict handling (Google/Outlook)
- Voice/call provider integration
- E-sign/document storage integration

## Recommended Next Build Order
1. Calendar and listing provider implementations
- Background sync jobs (pull updates + resilient retries/monitoring)
- MLS/IDX and Zillow provider implementations using live credentials

2. Provider rollouts
- Voice/call provider integration
- E-sign/document storage integration

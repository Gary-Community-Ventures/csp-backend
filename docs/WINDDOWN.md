# CSP (CAP Colorado Childcare Portal) Wind-Down & Restoration Guide

_Last updated: 2026-07-09. Contact: tlillis@garycommunity.org_

The CSP pilot (portal.capcolorado.org) was shut down in July 2026.
`portal.capcolorado.org` now 301-redirects to https://www.capcolorado.org/en/learnings
via a Cloudflare Redirect Rule. The production database is **kept alive** for research
(Appsmith and other tools read from it directly).

**We are keeping everything easily restorable through at least mid-August 2026.**
Do not delete Heroku apps or cancel third-party accounts before then without checking
with the team.

---

## Current state (as of 2026-07-09)

### Heroku (team `gary-builds`)

| App | State | Monthly cost |
|---|---|---|
| `csp-backend-prod` | All dynos scaled to 0. **App must not be deleted** — it owns the research Postgres. Research DB migrated to Essential-0 (`postgresql-vertical-80152`, alias BROWN) on 2026-07-09; old Standard-0 (`postgresql-objective-35132`, alias JADE) pending destroy after Appsmith switchover. | $5 (Essential-0) + $50 Standard-0 until destroyed |
| `csp-backend-staging` | Dynos scaled to 0. Redis deleted; Postgres (essential-0) intentionally kept through the restorable window (final backup also saved, see Backups). | $5 |
| `csp-frontend-prod` | Dynos scaled to 0. Custom domain `portal.capcolorado.org` no longer routes here (Cloudflare intercepts). | $0 |
| `csp-frontend-staging` | Dynos scaled to 0. | $0 |
| `csp-clickup` | Still running (Basic dyno). Not yet reviewed — likely a CSP↔ClickUp integration; shut down if confirmed CSP-only. | $7 |

Related but **intentionally kept alive** (not part of this wind-down):
- `cap-application-prod` + `cap-application-staging` (apply.capcolorado.org): 2 Basic dynos, no add-ons — **$14/mo total**.

### Money / Chek
- All family wallet balances reclaimed to the program (completed 2026-07-09; ~$2,900 total returned across the automated job + manual sweeps).
- 14 provider **card** balances intentionally left active — providers still spend from them.
- No outstanding provider payments (the one dangling March 2026 payment intent was confirmed retried and paid).
- Chek program (`CHEK_PROGRAM_ID`, account `acct_1S1DWAJEFUVAQKOx`) still open — see turn-off list.

### DNS (Cloudflare, zone capcolorado.org)
- `portal` → AAAA `100::`, proxied, with Redirect Rule `portal-shutdown-redirect` (301 → /en/learnings).
- `api.capcolorado.org` → still CNAMEs to Heroku (`csp-backend-prod`); dead while dynos are at 0. Remove record when fully decommissioning.
- ⚠️ `default._bimi` TXT points at `https://portal.capcolorado.org/bimi.svg` — broken by the redirect. Re-host the SVG or delete the record.

### Backups (also to be copied to org Google Drive, encrypted)
- `~/csp-winddown/csp-backend-prod-final-2026-07-09.dump` — prod Postgres (PG17 custom format, 19 tables, verified). NOTE: prod DB is still live; this is a point-in-time safety copy.
- `~/csp-winddown/csp-backend-staging-final-2026-07-09.dump` — staging Postgres final state (verified).
- Restore with: `pg_restore -d <target-db-url> <file>.dump` (requires PG16+ client tools).

---

## Restoration plan (spin the portal back up)

Everything below assumes the third-party services (Clerk, Chek, SendGrid/Postmark,
Twilio, Sentry, Supabase) have NOT been cancelled yet. If any were cancelled,
recreate the account and update the matching config vars first
(`heroku config -a <app>` still holds all current values — nothing was unset).

1. **Backend** (needs Redis back for the job queue):
   ```
   heroku addons:create heroku-redis:mini -a csp-backend-prod   # wait for it to provision; it re-attaches as REDIS_URL
   heroku ps:scale web=1:Standard-2X worker=1:Standard-1X scheduler=1:Standard-1X -a csp-backend-prod
   ```
   Scheduled jobs (monthly allocations, attendance, reminders, fund reclamation) re-register
   automatically from the scheduler process on boot.
2. **Frontend**:
   ```
   heroku ps:scale web=1:Standard-1X -a csp-frontend-prod
   ```
3. **DNS / routing** (Cloudflare):
   - Delete (or disable) the Redirect Rule `portal-shutdown-redirect`.
   - Point `portal` back at Heroku: replace the `100::` AAAA record with
     CNAME → `introductory-violet-uu8hwk5ueob2bv4fg1tf1w6e.herokudns.com` (proxied).
     If the Heroku domain was removed, re-add: `heroku domains:add portal.capcolorado.org -a csp-frontend-prod` and use the new DNS target it prints.
   - `api.capcolorado.org` CNAME → `quiet-bean-xkj5lfcgv1naw27pezr8mahc.herokudns.com` (unchanged as of this writing).
4. **Webhooks**: re-enable the Clerk webhook endpoint (api.capcolorado.org) if it was disabled.
5. **Staging** (optional): dynos are intact; its Postgres/Redis were deleted, so
   `heroku addons:create heroku-postgresql:essential-0 -a csp-backend-staging`, restore the
   staging dump if needed, `heroku addons:create heroku-redis:mini`, run `flask db upgrade`, scale up.

Time estimate: ~15 minutes for prod if third parties are still active.

---

## Third-party services still ACTIVE — future turn-off checklist

When we're confident we won't spin back up (target: after mid-August 2026):

- [ ] **Clerk** — production instance (auth). Paid plan + MAU billing. Downgrade/delete instance. Delete the webhook endpoint pointing at api.capcolorado.org (can be done sooner; it's dead weight while the API is down).
- [ ] **Chek** (chekspend.com, account `acct_1S1DWAJEFUVAQKOx`) — coordinate program closure with account manager. Provider cards must be resolved/emptied first (they are intentionally active today).
- [ ] **SendGrid** and/or **Postmark** — email. Both configured (`EMAIL_PROVIDER` selects; check which plan is paid). Cancel paid plans. Sender domains: notifications@/internal@capcolorado.org.
- [ ] **Twilio** — SMS. Release the phone number, close/downgrade account.
- [ ] **Sentry** — error tracking for csp-backend + csp-frontend. Delete projects; downgrade plan if CSP drove the tier.
- [ ] **Supabase** — hosts family/provider/child reference data the backend reads. ⚠️ May also be used by Appsmith research — confirm before deleting the project.
- [ ] **Google Cloud** — service account for Google Sheets sync. Revoke the key (free; hygiene).
- [ ] **Heroku final teardown** — delete `csp-frontend-prod`, `csp-frontend-staging`, `csp-backend-staging`, (`csp-clickup`?) app shells. `csp-backend-prod` + its Postgres live until research ends; final step is `pg:backups:capture` + download, then delete the app.
- [ ] **Cloudflare** — keep the zone (capcolorado.org is live); eventually remove the `api` record. Keep `portal` + redirect rule as long as the redirect should work.
- [ ] **GitHub** — archive `csp-backend` and `csp-frontend` repos (Gary-Community-Ventures org).
- [ ] **Appsmith** — retire the research dashboards when research concludes.

## Costs after this wind-down

- Heroku CSP: **$10/mo** (research DB $5 + staging DB $5) + $7 `csp-clickup` if kept.
  (Plus $50/mo Standard-0 until it is destroyed post-Appsmith-switchover:
  `heroku addons:destroy postgresql-objective-35132 -a csp-backend-prod --confirm csp-backend-prod`)
- apply.capcolorado.org (kept intentionally): **$14/mo**.
- Third parties: unchanged until the checklist above is executed.
- NOTE: Essential-tier DBs have no continuous protection/rollback — the encrypted dumps
  in Google Drive are the disaster-recovery copy. Restoration plan step 1 note: the research
  DB now lives on `HEROKU_POSTGRESQL_BROWN`; if the portal is revived, its connection limit
  is 20 — fine for the app, but consider re-upgrading if workers run heavy jobs.

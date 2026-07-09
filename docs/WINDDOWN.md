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
| `csp-backend-prod` | All dynos scaled to 0. **App must not be deleted** — it owns the research Postgres. Research DB migrated to Essential-0 (`postgresql-vertical-80152`, alias BROWN) on 2026-07-09; Appsmith switched over (verified via live connections) and the old Standard-0 destroyed the same day. | $5 (Essential-0) |
| `csp-backend-staging` | Dynos scaled to 0. Redis deleted; Postgres (essential-0) intentionally kept through the restorable window (final backup also saved, see Backups). | $5 |
| `csp-frontend-prod` | Dynos scaled to 0. Custom domain `portal.capcolorado.org` no longer routes here (Cloudflare intercepts). | $0 |
| `csp-frontend-staging` | Dynos scaled to 0. | $0 |
| `csp-clickup` | **Keep — NOT CSP-only.** GitHub→ClickUp issue sync (repo: `csp-clickup-webhook`) serving csp-backend/frontend AND rules_engine_mockup, rules-visualizer, home-ownership-navigator. Its cost belongs to org tooling. Optional cleanup: remove the two CSP repo entries from its mapping after the repos are archived. | $7 (shared) |

Related but **intentionally kept alive** (not part of this wind-down):
- `cap-application-prod` (apply.capcolorado.org): 1 Basic dyno, no add-ons — **$7/mo**.
  `cap-application-staging` scaled to 0 on 2026-07-09 (app shell kept, was $7/mo).

### Money / Chek
- All family wallet balances reclaimed to the program (completed 2026-07-09).
- Provider **card** balances intentionally left active — providers still spend from them.
- No outstanding provider payments (the one dangling March 2026 payment intent was confirmed retried and paid).
- Chek program still open — see turn-off list. (Account/program IDs are in the Heroku config vars and the internal copy of this doc.)

### DNS (Cloudflare, zone capcolorado.org)
- `portal` → AAAA `100::`, proxied, with Redirect Rule `portal-shutdown-redirect` (301 → /en/learnings).
- `api.capcolorado.org` → still CNAMEs to Heroku (`csp-backend-prod`); dead while dynos are at 0. Remove record when fully decommissioning.
- ⚠️ `default._bimi` TXT points at `https://portal.capcolorado.org/bimi.svg` — broken by the redirect. Re-host the SVG or delete the record.

### Backups
Final database dumps (prod research DB post-switchover, prod point-in-time, and staging)
were taken and verified on 2026-07-09 and are stored in secure internal storage — the
internal copy of this doc has the details; ask the team if you need access.
- Restore with: `pg_restore -d <target-db-url> <file>.dump` (requires PG16+ client tools).
- NOTE: the research DB is still live; dumps are disaster-recovery copies. Essential tier
  has no continuous protection/rollback — take an occasional `heroku pg:backups:capture`
  while research is active.

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
- [ ] **Chek** (chekspend.com) — coordinate program closure with account manager. Provider cards must be resolved/emptied first (they are intentionally active today).
- [ ] **SendGrid** and/or **Postmark** — email. Both configured (`EMAIL_PROVIDER` selects; check which plan is paid). Cancel paid plans. Sender domains: notifications@/internal@capcolorado.org.
- [ ] **Twilio** — SMS. Release the phone number, close/downgrade account.
- [ ] **Sentry** — error tracking for csp-backend + csp-frontend. Delete projects; downgrade plan if CSP drove the tier.
- [ ] **Supabase** — hosts family/provider/child reference data the backend reads. ⚠️ May also be used by Appsmith research — confirm before deleting the project.
- [ ] **Google Cloud** — service account for Google Sheets sync. Revoke the key (free; hygiene).
- [ ] **Heroku final teardown** — delete `csp-frontend-prod`, `csp-frontend-staging`, `csp-backend-staging` app shells (NOT `csp-clickup` — shared org tooling; NOT `csp-backend-prod` until research ends). Final step for the research DB: `pg:backups:capture` + download, then delete the app.
- [ ] **Cloudflare** — keep the zone (capcolorado.org is live); eventually remove the `api` record. Keep `portal` + redirect rule as long as the redirect should work.
- [ ] **GitHub** — archive `csp-backend` and `csp-frontend` repos (Gary-Community-Ventures org).
- [ ] **Appsmith** — retire the research dashboards when research concludes.

## Costs after this wind-down (final state, reached 2026-07-09)

- Heroku CSP: **$10/mo** — research DB $5 (Essential-0) + staging DB $5.
  (Was ~$235/mo before the wind-down.)
- `csp-clickup`: $7/mo — shared org tooling, not attributable to CSP.
- apply.capcolorado.org (kept intentionally): **$7/mo** (prod only; staging scaled to 0).
- Third parties: unchanged until the checklist above is executed.
- Restoration note: the research DB now lives on `HEROKU_POSTGRESQL_BROWN`; its
  connection limit is 20 — fine for the app, but consider re-upgrading the plan if the
  portal is revived and workers run heavy jobs.

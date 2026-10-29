# Ocean 6 HR branding

This optional presentation layer preserves native Frappe/ERPNext/HRMS records,
permissions, calculations, routes, authentication and statutory/legal notices.
The site must explicitly set JSON numeric `ocean6_branding=1` (or `true`).
Opting out restores the native identity and auth composition, including when
shared HRMS bundles were built with this app's conditional identity patch.

## Presentation boundaries

- `branding.py` uses native boot/navbar/payroll-icon data and website context.
  Auth child templates extend the installed login and password pages and wrap
  `super()`; original forms, recovery, validation, email-link controls and scripts
  remain authoritative. The red wave panel uses approved Ocean 6 artwork.
- `branding_renderer.py` extends only the standalone HRMS document's identity
  metadata. Browser/Apple titles, favicon/touch icon, theme color, manifest link
  and splash URLs are branded. Boot/CSRF, compiled script URLs and routes remain.
- The enabled-only `/ocean6-hr.webmanifest` returns `application/manifest+json`
  with `Cache-Control: no-cache`. It clones the built native manifest, retaining
  start URL, scope, ID semantics and display mode, and changes identity fields
  and icon URLs only. Opt-out makes this endpoint unavailable (404).
- All custom CSS is scoped to `html[data-ocean6-brand]`. Operational light tokens
  are warm `#F2F0EA`, ivory `#FFFEFB`, ink `#121212`, muted `#66645E`, border
  `#DDD8CD`, primary `#C51F2A` and hover `#991923`. Avenir Next/Helvetica Neue/system
  sans fallbacks retain native icon/code fonts. Native semantic statuses remain.
- The tiny `public/js/ocean6.js` only sets server-provided brand and email-link
  visibility attributes. It has no observer, text rewriting, API or auth logic.
  Desk keeps descriptive native route titles such as Malaysia Payroll; auth and
  HRMS use Ocean 6 HR titles and branded favicons.
- HRMS Login with Email Link is visible only when branding and the existing
  `System Settings.login_with_email_link` Check are enabled. It navigates to
  `/login?redirect-to=%2Fhrms%2Fhome#login-with-email-link`. No auth method is added:
  native Frappe validation, mail policy and post-email-login home/role routing
  remain unchanged. The query is preserved at the form; no custom post-token
  redirect is implemented or claimed. Password-disabled/email-only configurations
  no longer display an inaccurate no-login-methods message in the branded shell.

## Explicit narrow HRMS build patch

Pinned HRMS 16.16.0 offers no runtime hook for its Vue product headings or install
prompt. `build_hrms.mjs` is an app-owned Vite **source transform at compilation**,
not a runtime DOM replacement and not a vendor-source edit. It targets exactly:

```text
frontend/src/components/BaseLayout.vue
frontend/src/components/InstallPrompt.vue
frontend/src/views/Login.vue
```

Exact expected fragments/counts must match or the build fails. Explicit Vue setup
bindings select Ocean 6 HR headings, actual logos, the install label and existing
email-link entry point when opted in; native branches remain when opted out.
Forms, handlers, OTP/provider behavior, permissions, notifications and routing are
not replaced. Vue compiler tests verify setup bindings and native fallbacks.

The supported zero-argument `after_build` hook calls the wrapper. It loads the
installed HRMS Vite configuration with its existing dependency resolver, preserves
all native plugins including PWA `injectManifest`, builds to the original HRMS
frontend output and repeats the native index-to-`www/hrms.html` copy. These are
**generated build artifacts**, not source changes to installed vendor files.
A later HRMS-only build can overwrite this patch; run the payroll app hook last.

Required dependencies are existing Node/Vite/Vue/compiler-sfc/vite-plugin-pwa in
HRMS's frontend, plus Pillow from the pinned Frappe environment. No dependency pin,
Dockerfile, Compose, vendor source, service-worker source or new package changes
are introduced. The existing production Dockerfile copies the new package files
and its normal `bench build --production` runs this hook when this app is included.
Do not substitute an HRMS-only build for that final step.

`branding_assets.py` derives 192/512px icons and all 30 pinned Apple splash sizes
from approved PNG artwork, preserving every original splash media query. It does
not redraw the mark. The 32 images and `asset-list.json` receipt are generated in
`public/images/ocean6/pwa/`, ignored by Git, and included in the built image.
They must exist and match their receipt before accepting a candidate. Source
artwork is byte-for-byte from MCN's approved `deploy/nextcloud/runtime/branding/img`
(`ocean6-logo.png`, `waves.svg`) and the earlier approved wordmark/icon copies.
MCN is read only. The app remains GPL-3.0-or-later; upstream legal credits remain.

## Cache, worker and installation contract

CSS and JS URLs use `?v=20261029-6` in both hooks and the standalone head. Bump both
when editing these files. If changing artwork later, version the image paths/URLs as well; a CSS query bump alone does not invalidate long-cached PNGs. HRMS uses native Vite content-hashed bundles and the
original `/assets/hrms/frontend/sw.js`, classic registration, config query,
Workbox precaching/cleanup and Firebase background-notification code. No worker
scope, authentication cache rule, skipWaiting/clientsClaim policy or push behavior
is modified. No broad browser storage clearing, worker unregistration or session
invalidation is a release/rollback step.

A normal local update from native `index-BGng3SlX.js` to the branded compiled shell
was tested in the same profile: worker URL/scope unchanged, new bundle precached,
old precache entry removed and an isolated temporary storage probe retained. Only
that probe was removed afterward; actual stored-user-data migration was not tested.
Clean-profile manifest/icon parsing, native install prompt and activation passed.

**Inherited limitation:** the native manifest declares `/assets/hrms/frontend/`
scope while its start URL is `/hrms`; Chromium ignores that manifest scope and
normalizes it to `/`. The worker itself stays scoped to `/assets/hrms/frontend/`
and does not control the `/hrms` navigation document (`controller=null` observed).
This correction does not fix or broaden that boundary, so offline HRMS navigation
is not accepted here. Actual OS installation, existing home-screen name refresh,
iOS splash rendering and device-specific install/update UX remain device gates.
Do not clear storage/unregister workers to claim those passed.

## Validation and supported themes

Real local fictional manager/employee paths cover auth/recovery/email-link entry
without sending; workspace; populated/empty Employee list; Employee/Salary Slip
forms; readiness report; permitted TP1/TP3 and HRMS navigation; native blocked
manager-without-Employee state; native empty-login errors; keyboard focus; 1440px,
390px and a 150% zoom approximation. Mobile form tabs are genuinely scrollable,
with an added scrollbar cue; the clipped next label was not a missing tab.

Native Desk Frappe Light and Timeless Night were exercised; dark text/surfaces
were legible and the fictional manager's original Light preference was restored.
HRMS does not implement a complete native dark theme in this pinned version;
this change does not pretend that it does. Its branded supported shell remains
light. Guest and unrelated-employee Salary Slip requests remained 403; permitted
HR-manager read remained 200. No payroll/business record was saved/submitted.

Run from the app checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
npm run check:js
node --check malaysia_workforce/build_hrms.mjs
```

Run the Vue compiler tests and actual hook integration from the existing bench:

```bash
HRMS_FRONTEND="$PWD/apps/hrms/frontend" node --test apps/malaysia_workforce/malaysia_workforce/tests/build_hrms.test.mjs
bench build --apps malaysia_workforce --production
```

## Release and rollback boundary

This correction is an uncommitted review candidate relative to `8c839725`; no
production image build, publication, deployment, live reload or mail is approved.
Regenerate the index-based release manifest after staging exactly the correction
sources. Candidate image verification must include the transformed HRMS bundles,
head/manifest, both asset symlinks (`hrms` and `malaysia_workforce`), and the generated
PWA asset receipt, not just app source files or `assets.json`.

No migration is required: schema/fixtures/patches/installation hooks are unchanged.
Do not run `setup` (it migrates/reseeds), `install-app`, or `bench migrate` for this
UI diff. A future approved rollout must recreate image consumers and refresh
per-user boot plus website/browser caches. Set the site flag before new web
processes start to avoid a second reload; frontend must resolve healthy new
upstreams. Caddy/Nextcloud, DB/Redis and all business/user records are outside scope.

Rollback can restore the previous site flag and native shared-shell branches, or
restore the previous verified image through the approved process. Keep scope/ID
semantics and user storage intact. Refresh affected boot/website caches and use
ordinary browser/PWA update/reopen; device-visible metadata rollback is not
instant or guaranteed without device acceptance. No storage/session reset is a
shortcut. Mail remains disabled; password setup/login and the post-stack memory
baseline remain separate operational gates.

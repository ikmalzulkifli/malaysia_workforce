# Ocean 6 site branding

Ocean 6 branding is optional presentation for the existing Malaysia Payroll app.
It preserves native Frappe/ERPNext/HRMS screens, actions, permissions, calculations,
module identity, statutory warnings and legal notices. The generic app remains
unbranded unless the individual site explicitly sets `ocean6_branding` to numeric
`1` (JSON `true` also works).

## Implementation

- `branding.py`: native boot navbar and payroll desktop-icon data; website logo,
  favicon and asset inclusion. Existing website head content is retained.
- `branding_renderer.py`: supported `page_renderer` extension, selected only for
  the opted-in `hrms` endpoint. It adds the app's assets to the installed HRMS
  template source. The upstream controller, CSRF boot, manifest, compiled asset
  hashes and authentication remain authoritative. No vendor template is copied.
- `public/css/ocean6.css`: every selector is scoped to `html[data-ocean6-brand]`.
  Native variables cover Desk and web forms; Ionic variables cover HRMS.
- `public/js/ocean6.js`: enables that attribute only from the server's site opt-in.
  It does not call APIs, observe the DOM, change navigation, or replace text.
- Versioned asset URLs prevent an older stylesheet persisting in browser caches.
  Bump both hook and website-head URLs when changing these assets.

## Brand system

The operational UI uses Avenir Next, Helvetica Neue and system sans fallbacks.
Light surfaces use warm `#F2F0EA`, ivory `#FFFEFB`, ink `#121212`, muted `#66645E`,
and border `#DDD8CD`; primary actions use `#C51F2A` and hover `#991923`.
The original logo artwork keeps its own red. Dark-mode preferences remain native;
the theme supplies contrasting dark action colors rather than forcing light mode.
Native success, warning, error, disabled and workflow status semantics remain.

At 390px, login and native form controls have 44px minimum height. Existing mobile
navigation and contained report-table scrolling remain native. No dashboards,
financial figures, workflows, access-request controls or permission rules are added.

The two PNGs under `public/images/ocean6/` are byte-for-byte copies of the approved
MCN assets `apps/backend/public/images/brand/ocean6-banner.png` (wordmark.png) and
`ocean6-icon.png` (icon.png). MCN was read only. Source originals and usage guidance
are retained in that repository's `brand/ocean6/`. Do not distort the logo or use
the banner as a narrow app icon. Ocean 6 artwork is a brand asset, not a change to
the app's GPL-3.0-or-later licensing or upstream notices.

## Local verification

Validated on the existing local bench with pinned Frappe 16.31.0, ERPNext 16.31.1,
HRMS 16.16.0 and fictional actors/records. Login, workspace, populated Employee
list/form, Salary Slip form, Payroll Readiness report, empty list filter, employee
HRMS home, TP1/TP3 lists and mobile navigation were inspected. The HRMS manager
without an employee link retains its native blocked/login state. Employee access
was inspected with the existing employee fixture; no payroll records were saved,
submitted, cancelled, paid or distributed.

Automated checks cover opt-in isolation and preservation of unrelated app icons
and existing website-head content. Existing JavaScript syntax and Python suites
must also pass. Browser captures belong to the task outputs, not this release.

## Release plan (not executed)

1. Review the scoped diff and obtain separate deployment approval. This task does
   not authorize a UI release, live build/restart, migration or ingress change.
2. Build a candidate image from the reviewed branding commit through the existing
   release process, only after separate build approval. The branding commit includes
   the app-owned assets and regenerated release manifest; no candidate image has
   been built or published as part of local release preparation.
3. Validate the candidate and opt-in-off behavior in staging, including native
   light/dark preferences, login, actual permitted employee/HR/payroll records,
   mobile forms, navigation and reports. Retain user/tenant isolation denials.
4. For the approved site only, enable the JSON numeric setting using the existing
   deployment procedure. The local validation equivalent is:
   `bench --site test.localhost set-config ocean6_branding 1 --parse`.
   Refresh affected users' boot caches as well as website/browser caches after the approved asset
   rollout. Do not apply these commands to the pilot without deployment approval.
5. Confirm asset responses and populated behavior at 1440px and 390px. Check any
   installed HRMS PWA separately: existing service-worker caches and its upstream
   manifest/splash/icon/name are not replaced by this change.

Rollback presentation by restoring the previous site setting (or setting numeric
`0`) and refreshing affected users' boot and website/browser caches through the approved procedure. Application processes may also require the normal approved reload to refresh cached site configuration.
If image rollback is required, use the retained previous image and normal release
process. No payroll, user, statutory or employee records need modification.

Live admin creation and SMTP configuration are separate operational work; this
branding module neither creates accounts nor enables or sends email.

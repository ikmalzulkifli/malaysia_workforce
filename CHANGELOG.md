# Changelog

## Unreleased

- CP39 header now writes independent "Total MTD Records" and "Total CP38 Records" counts (Exhibit 4 fields 7 and 9) instead of the same number in both. An MTD-only employee no longer produces a CP38 count of one. Detail lines, including zero/zero employees, are unchanged pending HASiL confirmation on whether such lines should be omitted.
- Validated the bonus-only second-slip route end to end: a separate zero-basic Salary Structure with its own assignment (carrying the contract wage) produces a slip with only the Additional Salary bonus, and the month's PCB matches the single-slip case (RM24.60). A zero assignment base is rejected by the minimum-wage gate, so off-cycle bonus runs must keep the contract wage on the assignment.
- The zakat-offset explanation is no longer discarded: `calculate_pcb()` returns the constructed explanation, so the saved Salary Slip statutory result records why additional-remuneration MTD was reduced.

- Salary Slip statutory deductions are now authoritative. The app no longer calls `calculate_net_pay()` after writing its rows (which let Salary Structure components with the same name overwrite the statutory amount) and no longer skips calculation at submission. Managed rows are rewritten on every save and again at submit, then totals and net pay are recomputed once. A Salary Structure that contains EPF Employee, SOCSO Employee, SKBBK Employee, EIS Employee, PCB or CP38 can no longer change the payslip amount.
- Zakat is no longer an app-managed deduction. Re-appending it duplicated an Additional Salary zakat row on every save, so the employee was deducted twice while the PCB offset and filing showed one amount. The Salary Structure or Additional Salary row is left in place and used once.
- Statutory results store each slip's own wage contribution in the new `Malaysia Statutory Result.slip_wages` field. Same-month accumulation for SOCSO, EIS and HRD Corp now uses that value instead of the cumulative monthly `wage_base`, which compounded across slips (two RM2,000 slips produced RM6,000 of wages; three produced RM14,000 and over-levied HRD Corp). Filing wage columns and the scheme breakdown use the same per-slip value. Periods filed by an earlier build keep the cumulative base; preparing such a multi-slip period now fails closed with an explanation instead of exporting a guessed wage.
- TP1 C11 is split into C11A (voluntary EPF, RM4,000 including compulsory EPF) and C11B (life insurance/takaful or additional voluntary EPF, RM3,000). C11A relief is limited to the unused part of the RM4,000 EPF sublimit after the EPF relief already counted in P; C11B is independent. A lump-sum C11 claim is rejected at declaration save and at payroll, requiring explicit itemisation rather than an apportionment guess.
- Payroll Readiness, Payroll Entry submission and the readiness report now name any of the six managed Salary Components that has no account for the company, instead of failing later in the accrual journal.
- PCB helpers no longer import Frappe at module scope, so the pure test suite runs without a bench (the CI `pytest -q` job previously failed on this).
- Ambiguous legacy history now blocks payroll itself, not only filing preparation. When a month already contains two or more slips from an earlier build (cumulative wage bases, no per-slip marker), Salary Slip calculation and submission stop with a message naming the slips and scheme. Previously a new RM2,000 slip added to two old RM2,000 slips calculated on RM8,000 and over-levied HRD Corp. Single-slip legacy months remain usable.
- Additional-remuneration MTD now projects the year with Step [C] (the monthly MTD before the RM10 floor), as section D Step 1[E] of the 2026 specification requires. Previously a normal MTD below RM10 zeroed the annual normal projection, so the whole annual tax was charged as additional MTD: a RM3,700 earner with a RM1,000 bonus was charged the full annual tax of RM122.00 instead of the bonus's RM29.60 marginal share.
- Zakat now offsets additional-remuneration MTD exactly as HASiL's 2026 worked table requires (section E.5(ii)). Zakat is absorbed by the normal MTD actually payable after the RM10 floor; any remainder reduces the additional MTD instead of being over-withheld. The prior and current zakat test case now pays RM700.10 rather than RM727.20 for the same inputs.

## 1.0.0-rc.14 — 2026-08-20

- Rewrote the user guide as a role-first handbook (Employee, HR Manager, Accounts Manager, Auditor, System Manager) with bookmarks, a monthly checklist and a short troubleshooting table, instead of a long numbered setup manual.
- Made remaining review findings actionable in-product: Statutory Filing list titles (`EPF Jul 2026`), Portal Status wording vs Draft/Submitted, a Setup card on the Malaysia Payroll workspace so Contract is not only under CRM, helper text that PCB Treatment and Statutory Day Type override the nearby HRMS tax/overtime controls, and the relief-claim description column on TP1/TP3 grids.
- Reviewed every stakeholder workflow on the live site and tightened the screens that failed a first-pass UX check: employee TP1/TP3 relief codes are now a readable list, PCB Category options are labelled, Salary Slip statutory results have their own tab, LINDUNG totals hide on non-PERKESO filings, Payroll Readiness no longer looks empty when everyone is ready, and Check Statutory Setup confirms with a dialog instead of a disappearing alert.
- Derived SOCSO Category and EIS Eligible from Date of Birth instead of static fields, matching EPF's existing age-category pattern. SOCSO switches to Second Category and EIS stops applying from age 60; EIS applies from 18 up to but not including 60. Removed the EIS Eligible hard requirement for the `SOCSO + EIS — LINDUNG Optional` profile in Employee, Payroll Readiness and Salary Slip calculation, since a 60+ contractor now correctly has it auto-derived to false and must not be blocked from saving or being paid.
- Excluded rest-day and public-holiday hours from the 104-hour statutory overtime cap, per Employment Act 1955 s60A(4)(a)'s proviso. Every Overtime Slip previously counted these hours toward the same cap as ordinary overtime.
- Stopped Salary Slip calculation and submission for a non-resident employee. `calculate_pcb()`'s non-resident branch was a real, reachable 30%-flat-rate calculation, not a stub, but non-resident PCB was never reviewed for phase 1 and the docs already committed to stopping instead of estimating.
- Stopped Salary Slip calculation and submission for a leaver whose relieving date falls before 31 December of the payroll year. PCB's annual projection always assumes continued employment through December regardless of which month is being calculated, so a leaver any time before year end — not just within the slip's own period — breaks that assumption.
- Extended the installed-rule-pack review-date check (`reviewed_through`) to Salary Slip's own `before_submit`, not only Payroll Entry submission. A Salary Slip submitted without going through Payroll Entry could previously run current dates against an expired rule pack.
- Fixed LHDN PCB header record counts under-reporting: the header counted only detail records with a nonzero MTD/CP38 amount, while every applicable employee record still gets a detail line regardless of amount, so a zero-PCB low earner's line went uncounted.
- Unhid the Prepared Output field on Malaysia Statutory Filing so HR Manager and other read-permitted roles can see and download it; left Prepare/Reconcile button visibility unchanged since `prepare_filing()` itself requires `write`, which HR Manager does not have. Stopped stacking orphaned File attachments on re-prepare — the previous prepared File is now deleted before the new one is created.
- Blocked cancelling a Malaysia Statutory Filing once it is Reconciled or its Authority Status is Accepted.
- Scoped Salary Slip's filed-filing cancel block to employees actually included in that filing's Employee Totals, instead of blocking cancellation of any slip in the company and period regardless of whether that employee was in the filing at all.
- Fixed CP38 Amount Deducted/Balance going stale: they only recomputed when the Directive itself was saved, so a Salary Slip that deducted CP38 without the Directive being re-saved left both stale. A Salary Slip submit with a nonzero CP38 deduction now refreshes the matching Directive directly.
- Investigated whether Daily/Hourly employees are paid for a gazetted public holiday they do not work (Employment Act 1955 s60D(1)) — this is entirely computed by the underlying HRMS Salary Structure, outside this app's scope, and depends on whether it uses payment-days-based or attendance/Timesheet-hours-based components. Payroll Readiness now flags every Daily/Hourly employee for manual review of this rather than assuming either way.
- Fixed disabled-spouse PCB relief being granted regardless of PCB Category; it now requires Category 2, matching the base spouse relief it extends.
- Added EPF/SOCSO/EIS wage-base classification checks to Payroll Readiness for the Standard profile, matching the checks already run for the SOCSO + EIS profile. A Standard-profile Salary Structure could previously pass Readiness with zero components classified for EPF, SOCSO or EIS wages.
- Added the missing HRD Corp Optional (0.5%) lower-bound check: fewer than five Malaysian employees is now flagged, matching the already-enforced ten-employee Compulsory threshold.
- Employee `validate()` now requires the same Date of Birth, NRIC, SOCSO Category, EPF Member Number, Tax Identification Number and PCB Category fields Payroll Readiness already required, so an Employee can no longer be saved looking complete while Readiness would still flag it.
- Added deterministic ordering (`effective_from desc, creation desc`) to CP38 Directive lookups, and blocked saving a CP38 Directive whose active period overlaps another submitted Directive for the same employee.
- Fixed the EPF CSV `EM Share`/`EMP Share` header labels, a one-character difference risking column-swap on import, to `Employer Share`/`Employee Share`. Added digit-normalization for member and identity numbers and ASCII rejection for names, matching the LHDN and PERKESO exporters.
- Verified against PERKESO's own "Spesifikasi Format Text File Untuk SOCSO + EIS Contribution" v1.0 (22 July 2022) that the MyCoID/SSM company registration number field is genuinely optional (Mandatory: N); stopped requiring it. Added digit-normalization so a dashed NRIC fits the identification number field's 12-character limit.
- Added a data-integrity test proving the `float(money(...))`/`Decimal(str(...))` round-trip used on every Currency field write and read is exact, including at large aggregate-filing magnitudes and for values historically prone to binary-float representation error.
- Renamed every "Payroll Processor" reference in the user guide to the real HR Manager/Accounts Manager roles; no such role exists in the app.
- Added an HR-Manager-gated Send for Review transition on the TP1/TP3 workflow, distinct from the existing employee self-service one, so HR can initiate the handoff on behalf of an employee with no self-service access. The existing self-service transition and the separate Approve gate are unchanged.
- Added a relief-code legend to the TP1 and TP3 web forms explaining each controlled relief code's label, and added the same Desk relief-code catalog loader TP1 already had to TP3, which previously had none.
- Gated the Malaysia Statutory Filing Reconcile button on Authority Status = Accepted; it was previously offered for a still-Pending or Rejected submitted filing.
- Added descriptions to the PCB Category and SOCSO Category fields on Employee.
- Added NRIC and the company's HRD Corp registration class/number to the HRD Corp levy working paper, and relabeled its Prepare button to "Prepare Working Paper" to reflect that HRD Corp has no portal upload, unlike the other three authorities.
- Added a "Malaysia Statutory Filing Working Paper" print format with control totals, a scheme-split breakdown computed at render time, the Employee Totals table, and an 8-character verification fragment of the prepared file's hash for maker/checker sign-off.
- Removed 28 empty, untracked doctype directories left over from the pre-lean schema, and noted in the README that the Frappe Module and app-title naming split is intentional.

This remains a release candidate. Clean official-stack bootstrap, external authority UAT, parallel payroll, recovery/security drills and Malaysian payroll-specialist sign-off are still required before live payroll.

## 1.0.0-rc.13 — 2026-08-18

- Added the explicit `Statutory Profile` field on Employee. `SOCSO + EIS — LINDUNG Optional` keeps contractors in standard Frappe HR records while calculating only SOCSO, EIS and applicable LINDUNG.
- Excluded that profile from EPF, LHDN and HRD Corp calculations and filings, blocked tax declarations and CP38, and added profile-aware payroll readiness and filing fingerprints.
- Documented the contractor setup and monthly workflow in the beginner user guide.
- Granted HR Manager and Auditor permlevel-1 read of the Salary Slip Statutory Profile snapshot so the field is visible after payroll.
- Added a Statutory Profile column and a default-off Show All Statutory Profiles filter to Malaysia Annual Remuneration, and stopped both payroll reports from losing the profile through `get_list` field permissions.
- Rejected a direct Salary Slip submit when the saved profile snapshot no longer matches the Employee.
- Stopped HRMS `calculate_net_pay` from putting Salary Structure Zakat back onto a contractor slip at submit.
- Showed **Applicable** on the Salary Slip statutory-results grid and moved the Statutory Profile snapshot above that table.
- Filled the Company filter on payroll reports from the user's sole Company permission when no default is set, and granted System Manager read/select/report on Employee, Salary Slip and Payroll Entry so those report roles can actually run.
- Directed employees to **View Salary Slips** on HRMS home instead of the blank `/hrms/home/salary` route.

## 1.0.0-rc.12 — 2026-08-16

- Repaired upgrades from pre-lean schemas that retained permission rows for retired localization roles whose Role records no longer exist. The migration now removes only those orphaned rows before Frappe refreshes Employee Self Service permissions and still stops if a user carries a retired role.

## 1.0.0-rc.11 — 2026-08-13

- Fixed employee payslip PDF downloads on hosts without `wkhtmltopdf` by selecting Frappe v16's native headless-Chrome renderer through a narrowly scoped HRMS endpoint hook.
- Kept `wkhtmltopdf` as the first choice when the host provides it and documented production Chromium provisioning and PDF smoke testing.

## 1.0.0-rc.10 — 2026-08-13

- Completed the native employee TP1/TP3 handoff: the standard Web Form now saves the declaration and immediately applies Frappe's `Send for Review` Workflow action, with retry-safe server authorization and a clear success page.
- Derived hidden Employee and Company values from the signed-in active Employee on the server, removing browser-only mandatory-field failures without trusting client input.
- Added a narrow upgrade patch for missing TP1/TP3 Workflow submit rights while preserving unrelated administrator permission customizations.
- Supported one signed TP3 per distinct previous employer and employment period, with duplicate prevention and combined annual relief caps across every approved TP3 and the current-employer TP1.
- Added labels and field types to native Web Form lists, removing `undefined` headings.
- Added MariaDB coverage for employee submission, retry safety, HR approval and multiple previous employers, plus Chrome mobile acceptance for both tax Web Forms.

This remains a release candidate. Clean official-stack bootstrap, external authority UAT, parallel payroll, recovery/security drills and Malaysian payroll-specialist sign-off are still required before live payroll.

## 1.0.0-rc.9 — 2026-08-13

- Corrected LINDUNG 24 Jam from an opt-in election to the opt-out scheme PERKESO confirmed on 10 July 2026. Participation is now the default: an employee who has recorded nothing contributes, and the deduction stops only from the effective date of their own Liability Release Notice. The previous model blocked payroll for every employee whose participation was unrecorded, which after the rc.8 migration was all of them.
- A release cannot take effect before 8 July 2026, so already-deducted June 2026 contributions are never reversed.
- Evidence and an effective date are now required only for a recorded release, not for the default.
- Fixed a mid-month over-deduction: SKBBK was folded into the SOCSO scheme total instead of being tracked separately, so a second Salary Slip in the same month re-charged SKBBK that the first had already taken while over-reducing SOCSO. On an even RM3,000/RM3,000 September split this charged RM22.15 too much SKBBK and RM15.00 too little SOCSO, and left the PERKESO filing totals disagreeing with the payslips; the amount varies with how the month is split, up to a full band.
- Fixed the payroll-readiness live scenario, which passed its filter as `on_date` and so evaluated readiness against the current date instead of the period end.
- Enforced Company/User Permissions in payroll reports and rejected unclassified earning components before statutory calculation.
- Enforced the official existing/new-employee LINDUNG release windows and failed closed for unsupported multiple-employer selection.
- Reconciled HRD Corp registration against the Malaysian-employee threshold and excluded permanent residents from leviable employees.
- Aggregated Overtime Slip detail hours by calendar month for the 104-hour limit.
- Included employee and employer identifiers in statutory-filing fingerprints so identity changes invalidate prepared files.
- Replaced the arbitrary TP3 relief total with controlled, evidenced relief rows sharing annual limits with TP1.
- Stopped automatic legacy-role mapping from granting broader HR/accounting permissions.
- Corrected CP38 remaining-balance handling across multiple Salary Slips in one month.

**Action required on upgrade.** A migration sets every `Not Set` employee to `Participating` and clears election paperwork left on participating employees; the underlying File records are preserved on the Employee. Employees already recorded as `Not Participating` are left untouched and written to the error log, because this app cannot tell a genuine portal Liability Release Notice from an election captured under the old model — **re-verify each one before the next payroll**. Submitted Salary Slips are not recalculated: review every slip since 1 June 2026 that recorded zero LINDUNG, and any employee with two slips in one month, and correct them through the documented amendment process.

## 1.0.0-rc.8 — 2026-08-12

- Rebuilt the app as a lean Malaysian payroll localisation around standard Frappe HR records.
- Removed the custom staffing, availability, roster, kiosk, employee-profile, work-agreement, bank, incident, privacy, accumulator and parallel-payroll subsystems.
- Added a guarded migration that stops when real legacy operational records need an explicit archive or migration decision.
- Added Malaysia fields to standard Company, Employee, Contract, Salary Component, Salary Slip, Payroll Entry and Overtime Type records.
- Added effective-dated EPF, SOCSO/SKBBK, EIS, PCB, HRD Corp, minimum-wage and wage-rule calculations.
- Added TP1, TP3, CP38, statutory filing, payroll-readiness and annual-remuneration features using native Frappe forms and reports.
- Added source-hash protection, two-person payroll release and read-only auditor access.
- Added deterministic live MariaDB scenarios, including post-validation source-tamper rejection.
- Pinned the tested Frappe 16.31.0, ERPNext 16.31.1 and HRMS 16.16.0 stack.
- Recorded the upstream Frappe clean-site bootstrap defect honestly as a production release blocker.

The prior implementation remains preserved on branch `codex/archive-pre-lean-20260812` at commit `5fce234`.

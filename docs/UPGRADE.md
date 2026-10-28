# Upgrade

## From the pre-lean release candidate

The migration preflight stops if any abandoned custom operational DocType contains records, including old staffing plans, availability, custom profiles/agreements, Malaysia Payroll Runs, Shift Work Records, accumulators or submissions.

Before upgrading:

1. Back up and test restoration.
2. Export and reconcile genuine legacy records.
3. Decide what must be retained as attachments/audit archives and what maps to standard Employee, Contract, Payroll Entry or Salary Slip.
4. Remove operational legacy rows only through a reviewed migration procedure.
5. Retry migration in staging.

The same preflight stops when any legacy app role is still assigned. There is no automatic mapping because standard HR and accounting roles may grant broader access. An administrator must assign the intended standard roles, verify Company User Permissions, remove the legacy roles from each User, and retry.

The app never guesses how to merge legally relied-upon payroll records.

After the preflight passes, schema sync removes obsolete DocTypes and the app removes only its known legacy Custom Fields. It preserves unrelated administrator customization. Reserved Malaysia Salary Components keep administrator account/formula configuration while their app-owned statutory metadata is refreshed.

## From 1.0.0-rc.14 (per-slip wage bases and C11)

`Malaysia Statutory Result` gains `slip_wages` and `per_slip_wages_recorded`, and TP1 C11 becomes C11A/C11B.

Salary Slips submitted by rc.14 and earlier store only the cumulative monthly wage base for SOCSO, EIS and HRD Corp. A month with a single slip is still exact. A month with **two or more** slips cannot be reconstructed without guessing, so payroll now stops at calculation and submission with a message naming the affected slips and scheme. It is not enough to leave those periods unfiled: filing them under the old build would export the known overstated wage base.

Correct them deliberately, with review:

1. Identify affected employees from the error message (or from `Malaysia Statutory Result` rows with `per_slip_wages_recorded` unset where more than one slip shares the month and scheme).
2. Recomputed contributions may differ from what was deducted. Decide the employee/employer correction with your accountant before amending or issuing a payroll correction.
3. Amend the affected slips through the standard cancel/amend process so the current build recalculates and stamps `slip_wages`. Do not edit `wage_base`, `slip_wages` or `per_slip_wages_recorded` by hand.
4. Re-prepare any draft filing after the slips are corrected. Submitted or reconciled filings keep their recorded totals and must be corrected through the authority's own amendment process.

TP1 rows saved with the old lump-sum `C11` must be amended into `C11A` (voluntary EPF, RM4,000 including compulsory EPF) and `C11B` (life insurance/takaful or additional voluntary EPF, RM3,000). Payroll refuses to run with a legacy row rather than allocating it.

No submitted payroll or statutory result is rewritten by the upgrade.

## From 1.0.0-rc.8

This release corrects LINDUNG 24 Jam from an opt-in election to an opt-out scheme. A migration sets every employee whose participation is blank or `Not Set` to `Participating`, and clears the effective date and evidence on participating employees. Only the field values are cleared; the attached File records remain on the Employee.

Employees already recorded as `Not Participating` are **left untouched and written to the error log** under "LINDUNG 24 Jam releases need re-verification". The app cannot distinguish a genuine PERKESO Liability Release Notice from an election captured under the previous model, and only the employee can release the liability, so it will not re-enrol anyone. Re-verify every listed employee against an actual notice before the next payroll; anyone who never filed one is still participating and is being under-deducted.

Submitted Salary Slips are never recalculated. Before the next run, review every slip since 1 June 2026 recording zero LINDUNG, and every employee with two slips in one month (which the mid-month SKBBK fix also affects), and correct them through the documented amendment process.

Any legacy TP3 `Prior TP1 Reliefs` lump sum must be moved into itemised relief rows with official codes and evidence. Payroll rejects the old aggregate because it cannot prove per-code eligibility or annual limits.

## From 1.0.0-rc.9

A one-time patch adds the native Workflow submit/cancel/amend rights that rc.9 omitted from existing TP1 and TP3 Custom DocPerm rows. It changes only those rights for System Manager and HR Manager, preserves unrelated administrator permission customizations, and keeps Employee Self Service limited to its own draft declarations.

Employees can now use **Send for Review** directly from the standard TP1/TP3 Web Forms. Each distinct previous employer uses a separate TP3; the upgrade does not split or invent identities in existing records.

## Every upgrade

Use the compatibility lock, review upstream release notes, migrate twice, rebuild assets, run pure and live scenarios, compare payroll in parallel, rerun authority UAT if serialization changed, and obtain rule-pack review when statutory data changed.

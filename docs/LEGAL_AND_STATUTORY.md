# Statutory scope

## Included

- EPF Third Schedule categories for supported Malaysian citizens/permanent residents and age bands.
- SOCSO first/second category plus LINDUNG 24 Jam, which applies from 1 June 2026 and stops only from the effective date of an employee's own PERKESO Liability Release Notice. Per the official FAQ dated 13 July 2026: voluntary for local workers from 8 July 2026 and mandatory for foreign workers (Q3); declining is the only act that needs recording (Q5); June 2026 is mandatory and non-refundable (Q8); the employee bears the whole 0.75%, with no employer share (Q25).
- EIS contribution schedule and eligibility switch.
- LHDN resident PCB with regular/additional remuneration, TP1, TP3, zakat rebate and CP38. The 2026 computerised MTD formula, B values and text-file layout were checked against HASiL's "Spesifikasi Kaedah Pengiraan Berkomputer PCB 2026" (updated 1 January 2026).
- TP1 C11 split into the two s.49(1)/(1A) sublimits: C11A voluntary EPF (RM4,000 including compulsory EPF already relieved by the formula) and C11B life insurance/takaful or additional voluntary EPF (RM3,000), total RM7,000.
- HRD Corp 1% or 0.5% levy according to configured registration class, with the compulsory class enforced from ten Malaysian employees.
- Minimum Wage Order effective dates.
- Full-time ordinary hourly rate, normal overtime, rest-day, public-holiday, incomplete-month and termination-benefit primitives.
- Part-time rule data and Contract validation.

Every rule table is checksum-protected and included in `source_manifest.json`. Calculations stop after the reviewed-through date.

### Public holiday pay boundary

The "public-holiday... primitive" above (EA1955 s60D(3)) is the premium for a holiday actually **worked**; it is verified correct for every wage basis, monthly through hourly, including the part-time Regulation 6 variant. The separate s60D(1) entitlement — one ordinary day's wage for a gazetted public holiday a Daily- or Hourly-rated employee does **not** work — is outside this app's scope, because base pay for those wage bases is computed entirely by the underlying HRMS Salary Structure, not by this app. Whether that entitlement is actually paid depends on whether the Salary Structure's earning components are payment-days-prorated (paid, given this app's forced `include_holidays_in_total_working_days`) or attendance/Timesheet-hours-based (not paid, since an unworked day logs no hours). This cannot be determined from data, so Payroll Readiness flags every Daily/Hourly employee for manual review rather than assuming either way — see `docs/USER_GUIDE.md`, "Daily and Hourly base pay, and unworked public holidays."

### LINDUNG 24 Jam boundaries

The employee release windows are enforced from the official PERKESO FAQ:

- **Declaration windows.** Existing employees can be recorded as released only from 13 July through 31 August 2026 (Q16). A newly registered local employee has 30 days from PERKESO registration to decline (Q22). After the applicable window, payroll fails closed rather than accepting a late release.
- **Multiple employers.** PERKESO permits only the selected employer to deduct LINDUNG. Phase 1 records that the employee has multiple employers and blocks automatic payroll for the case; it does not guess which employer PERKESO selected.
- **Rate phases.** 0.75% applies 1 June 2026 – 31 May 2028, then 1.00% to 31 May 2031, then 1.25% (Q23). Only the 0.75% phase is in `socso_skbbk_2026.csv`, which is safe while `reviewed_through` precedes June 2028.
- **June 2026 arrears.** If June was not deducted for a participant, the employer owes the arrears (Q18). The app has no arrears mechanism; handle it as an ordinary Additional Salary deduction after review.
- **Employer grace period.** PERKESO allows employers six months from enforcement free of penalty for LINDUNG non-compliance (Q31).

## Deliberately unsupported in Phase 1

- Sabah and Sarawak employment-law rules.
- Foreign-worker, non-resident and special tax regimes. Foreign workers remain mandatorily covered by LINDUNG 24 Jam with no release available.
- Expatriate, director-fee, share-option and other specialist PCB cases not represented by the tested input model.
- Automatic government submission, payment acknowledgement or legal-form signing.
- Final-pay orchestration, EA/e-Filing acceptance and every termination exception as an automated workflow.

Unsupported cases must be handled outside automatic calculation after professional review; they must not be forced through the ordinary rule path.

## Employer statutory accounting (known gap)

The app calculates and reports employer EPF, SOCSO, EIS and HRD Corp amounts on every Salary Slip and in every statutory filing, but it does **not** post them to the ledger. HRMS builds its payroll accrual journal from Salary Slip earnings and deductions, and employer contributions are neither, so the payroll journal carries only employee deductions and net pay. Employer statutory cost (roughly 13-16% of payroll) is therefore absent from the P&L and the statutory liability accounts unless it is posted separately.

Smallest supported approaches, pending an accounting decision:

1. **Manual journal per payroll period** (recommended for now): Dr employer statutory expense / Cr EPF, PERKESO, EIS and HRD Corp payable, using the employer amounts on the period's Salary Slips or filing preparation records. The filing control totals give the amounts to reconcile against.
2. **Customer-configured employer Salary Components** in the Salary Structure. This posts through the standard HRMS journal, but those components are calculated by HRMS formulas, not by this app, so they must be reconciled to the statutory results and will drift if rates change.

Whichever is chosen, reconcile the journal to the EPF/PERKESO/HRD filing employer totals every period. Do not assume the payroll ledger already contains employer contributions.

## Source governance

An authorised Malaysian payroll reviewer must compare every new rule pack to the current official EPF, PERKESO, LHDN, HRD Corp and JTKSM source, record the effective date and worked examples, update checksums, and approve the review deadline. Software tests support this review but do not replace it.

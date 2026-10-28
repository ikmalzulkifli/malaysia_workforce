# Payroll operations

## Monthly run

1. HR Manager resolves the Payroll Readiness report and reviews valid TP1/TP3 declarations that have reached Pending Review through the supported employee workflow, plus CP38 changes. Draft declarations do not affect payroll.
2. Payroll processor creates the standard Payroll Entry, uses `Get Employees`, then selects `Check Statutory Setup`.
3. Fix every named issue. Submission is blocked while setup is incomplete or the installed rule review has expired.
4. Submit Payroll Entry and create/submit Salary Slips through normal HRMS actions.
5. Review each Salary Slip's deductions and `Statutory Results` table.
6. Complete the normal Frappe HR payroll and accounting workflow with the organisation's maker/checker approvals.

Payslip PDF downloads use Frappe's standard renderer selection: `wkhtmltopdf`
when available, otherwise the native headless-Chrome renderer. Treat a failed
PDF as an infrastructure alert and check the renderer binary and worker logs;
it does not change the stored Salary Slip calculation.
7. For an off-cycle slip that pays only a bonus, use a separate Salary Structure with no basic pay and give its Salary Structure Assignment the employee's contract wage. A zero assignment base is blocked by the minimum-wage check, while the structure itself determines that only the Additional Salary is paid.
8. Post the employer statutory cost for the period (EPF, SOCSO, EIS, HRD Corp) as a separate journal, or maintain reconciled employer Salary Components. The payroll accrual journal does not include employer contributions; see `LEGAL_AND_STATUTORY.md`, "Employer statutory accounting".
9. Continue with the bank's approved payment procedure. This app does not transmit money.

## Overtime and special days

Use standard HRMS Overtime Types and set their `Statutory Day Type` to Normal Overtime, Rest Day or Public Holiday. The approved Overtime Slip produces normal Additional Salary. The app calculates the rate from the effective Contract and rejects unsupported cases.

## Authority preparation

Create one Statutory Filing per Company, authority and period. `Prepare File` derives totals from submitted Salary Slips and attaches a private output through standard Frappe Files. Review and upload it manually, submit the Frappe record, attach the receipt and acknowledgement, record the authority result, then reconcile. A changed source requires an amendment.

EPF, PERKESO and LHDN monthly formats are serialization adapters. HRD Corp is a reconciliation worksheet. All require external UAT.

## Corrections

- Before Salary Slip submission: correct the standard source record, regenerate/review and revalidate.
- After submission/accounting: use normal Frappe cancellation and amendment controls; do not edit submitted results directly.
- After filing: preserve the original filing and create an amendment.

Review sources before the deadline, reconcile every authority total, keep evidence private, review permissions quarterly and test restores.

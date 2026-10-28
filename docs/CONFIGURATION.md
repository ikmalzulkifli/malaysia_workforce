# Configuration

Configure standard Frappe HR first; then complete the statutory sections added to the same records.

## 1. Company

On the standard Company form, open `Statutory Payroll`:

- set Country to Malaysia and enable Statutory Payroll;
- keep Phase 1 jurisdiction as Peninsular Malaysia;
- enter SSM, LHDN, EPF and PERKESO employer identifiers;
- select the actual HRD Corp registration class and effective date;

In Payroll Settings enable `Include holidays in Total no. of Working Days`; the app requires this for Malaysia calendar-day incomplete-month treatment.

## 2. Employee

Use the standard Employee form. Open `Statutory Details` and enter citizenship status, NRIC, tax ID, EPF member number, SOCSO category, EIS eligibility and PCB status. LINDUNG 24 Jam participation is the statutory default from 1 June 2026 and needs no entry. Record `Not Participating`, the PERKESO registration date, release effective date and notice only when the employee personally filed a PERKESO Liability Release Notice. Mark `Has Multiple Employers` when applicable; phase 1 then stops payroll rather than guessing PERKESO's selected employer.

Link the Employee to a User whose User Type is `Employee Self Service`. Employees sign in through `/login?redirect-to=/hrms/home` for Frappe HR's mobile/PWA. TP1 and TP3 notifications should link directly to `/my-tax-reliefs/new` and `/my-previous-employment/new`; there is no custom employee portal.

Create a standard Payroll Period covering the payroll year. The HRMS PWA filters Salary Slips through Payroll Period; without one, submitted slips exist in Desk but the employee sees `No salary slips found`.

These fields are restricted at permission level 1. Phase 1 rejects foreign-worker and unsupported-jurisdiction cases instead of estimating them.

## 3. Employment terms

Use the standard ERPNext `Contract`; do not create a separate work-agreement record. Complete wage basis, full-time/part-time classification, contract rate, normal daily/weekly hours, rest day and overtime eligibility. A part-time Contract also needs comparable full-time weekly hours.

Use standard Salary Structure and Salary Structure Assignment for payroll amounts. The Contract is rules context, not a second salary structure.

## 4. Salary components

For every earning, select its EPF, SOCSO, EIS and HRD wage treatment, PCB treatment, and ordinary-rate treatment. Configure standard HRMS Overtime Types for normal overtime, rest-day work and public-holiday work, select the corresponding `Statutory Day Type`, and use normal Salary Components. The app creates only the deductions it owns: EPF Employee, SOCSO Employee, SKBBK Employee (the LINDUNG 24 Jam amount in the current PERKESO text specification), EIS Employee, PCB and CP38. Configure their Company accounts without renaming them: Payroll Readiness and Payroll Entry submission both stop and name any component that has no account for the company.

Those six components are recalculated on every Salary Slip save and again at submission. If a Salary Structure also contains one of them, the structure row is replaced by the statutory amount; the structure value is never used. Keep them out of Salary Structures to avoid confusing the component list.

Zakat is **not** app-owned. It stays an ordinary Salary Structure or Additional Salary deduction and is counted exactly once, both as a cash deduction and as the PCB zakat offset (provided the employee's zakat is deducted through payroll).

## 5. Tax inputs

Employees prepare TP1 for optional reliefs and one TP3 for each previous employer that paid them in the same tax year. Prior TP1 reliefs on every TP3 must be itemised with the same controlled codes and evidence; the app enforces one combined annual limit across all approved TP3 records and the current TP1. Selecting **Send for Review** saves the Web Form and applies Frappe's native Workflow transition to Pending Review. HR Manager approves or returns each declaration after reviewing its evidence. HR Manager records CP38 directly from the LHDN directive.

## 6. Standard HRMS payroll

Maintain Holiday Lists, Fiscal Years, Salary Structures, Salary Structure Assignments, Additional Salary and Overtime Slips in HRMS/ERPNext. The app does not duplicate these records.

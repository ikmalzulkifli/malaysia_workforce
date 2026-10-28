from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import getdate

from malaysia_workforce.payroll.profile import (
	SOCSO_EIS_LINDUNG_PROFILE,
	STANDARD_PAYROLL_PROFILE,
	STATUTORY_PROFILE_FIELD,
	normalize_statutory_profile,
	scheme_applies,
)
from malaysia_workforce.payroll.validation import (
	employee_statutory_profile,
	epf_socso_eis_earning_component_issues,
	hrd_registration_issues,
	lindung_payroll_issues,
	missing_component_account_issues,
	required_identity_field_issues,
	socso_eis_earning_component_issues,
	unclassified_earning_components,
)
from malaysia_workforce.statutory.rule_pack import assert_rule_pack_covers


def _employee_names(doc) -> list[str]:
	return sorted({row.employee for row in (doc.employees or []) if row.employee})


def employee_readiness(employee: str, company: str, on_date) -> list[str]:
	"""Return actionable setup errors without creating or changing any document."""
	errors: list[str] = []
	row = frappe.db.get_value(
		"Employee",
		employee,
		[
			"company",
			"status",
			"date_of_birth",
			"custom_malaysia_citizenship_status",
			"custom_tax_identification_number",
			"custom_nric",
			"custom_epf_member_number",
			"custom_socso_category",
			STATUTORY_PROFILE_FIELD,
			"custom_lindung_participation",
			"custom_lindung_registration_date",
			"custom_lindung_effective_from",
			"custom_lindung_evidence",
			"custom_lindung_multiple_employers",
			"custom_pcb_category",
		],
		as_dict=True,
	)
	if not row or row.company != company:
		return [_('Employee does not belong to this Company.')]
	if row.status != "Active":
		errors.append(_("Employee is not Active."))
	if row.custom_malaysia_citizenship_status not in {"Malaysian Citizen", "Permanent Resident"}:
		errors.append(_("Citizenship is outside the supported payroll scope."))
	profile = normalize_statutory_profile(row.get(STATUTORY_PROFILE_FIELD))
	if profile not in {STANDARD_PAYROLL_PROFILE, SOCSO_EIS_LINDUNG_PROFILE}:
		errors.append(_("Select a valid Statutory Profile."))
	errors.extend(required_identity_field_issues(row, profile))
	errors.extend(lindung_payroll_issues(row))

	assignment = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", on_date]},
		["name", "salary_structure"],
		as_dict=True,
		order_by="from_date desc, creation desc",
	)
	if not assignment:
		errors.append(_("No submitted Salary Structure Assignment covers the payroll date."))
	else:
		component_names = frappe.get_all(
			"Salary Detail",
			filters={
				"parent": assignment.salary_structure,
				"parenttype": "Salary Structure",
				"parentfield": "earnings",
			},
			pluck="salary_component",
		)
		if scheme_applies(profile, "PCB"):
			unclassified = unclassified_earning_components(component_names)
			if unclassified:
				errors.append(
					_("Set PCB Treatment for earning components: {0}.").format(", ".join(unclassified))
				)
			errors.extend(epf_socso_eis_earning_component_issues(component_names))
		else:
			errors.extend(socso_eis_earning_component_issues(component_names))

	contracts = frappe.get_all(
		"Contract",
		filters={
			"party_type": "Employee",
			"party_name": employee,
			"status": "Active",
			"start_date": ["<=", on_date],
		},
		fields=[
			"name",
			"end_date",
			"custom_malaysia_wage_basis",
			"custom_malaysia_work_classification",
			"custom_contract_wage_rate",
			"custom_normal_hours_per_day",
			"custom_normal_hours_per_week",
			"custom_comparable_full_time_hours_per_day",
			"custom_comparable_full_time_hours",
		],
		order_by="start_date desc",
	)
	contract = next((item for item in contracts if not item.end_date or getdate(item.end_date) >= getdate(on_date)), None)
	if not contract:
		errors.append(_("No active ERPNext Contract covers the payroll date."))
	elif not all(
		(
			contract.custom_malaysia_wage_basis,
			contract.custom_malaysia_work_classification,
			contract.custom_normal_hours_per_day,
			contract.custom_normal_hours_per_week,
		)
	):
		errors.append(_("The active Contract has incomplete Statutory Working Terms."))
	elif contract.custom_malaysia_wage_basis in {"Daily", "Hourly"} and not contract.custom_contract_wage_rate:
		errors.append(_("The active daily or hourly Contract is missing its rate."))
	elif contract.custom_malaysia_work_classification == "Part-time" and not all(
		(
			contract.custom_comparable_full_time_hours_per_day,
			contract.custom_comparable_full_time_hours,
		)
	):
		errors.append(_("The active part-time Contract is missing comparable full-time hours."))

	try:
		from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

		get_holiday_list_for_employee(employee, on_date)
	except frappe.ValidationError:
		frappe.clear_last_message()
		errors.append(_("No Holiday List is assigned for the payroll date."))
	try:
		from erpnext.accounts.utils import get_fiscal_year

		get_fiscal_year(on_date, company=company)
	except frappe.ValidationError:
		frappe.clear_last_message()
		errors.append(_("No active Fiscal Year covers the payroll date."))
	return errors


def _wage_basis_notes(employee: str, on_date) -> list[str]:
	"""Non-blocking flags for setups this app cannot verify from data alone.

	Base pay for Daily/Hourly-rated employees is computed by the ordinary HRMS Salary
	Structure, outside this app's scope. Whether an unworked gazetted public holiday is
	still paid (EA1955 s60D(1)) depends on which HRMS wage mechanism the Salary Structure
	uses: a payment-days-prorated component already pays it, since this app requires
	'Include holidays in Total no. of Working Days' to stay enabled; an attendance- or
	timesheet-hours-based component does not, since no hours are logged for a day nobody
	worked. This cannot be checked from data, so it is flagged for manual review rather
	than silently assumed either way.
	"""
	contracts = frappe.get_all(
		"Contract",
		filters={"party_type": "Employee", "party_name": employee, "status": "Active", "start_date": ["<=", on_date]},
		fields=["end_date", "custom_malaysia_wage_basis"],
		order_by="start_date desc",
	)
	contract = next((item for item in contracts if not item.end_date or getdate(item.end_date) >= getdate(on_date)), None)
	if contract and contract.custom_malaysia_wage_basis in {"Daily", "Hourly"}:
		return [
			_(
				"Daily/Hourly base pay is outside this app's scope. Confirm the Salary Structure pays an "
				"ordinary day's wage for gazetted public holidays this employee does not work."
			)
		]
	return []


def readiness(doc) -> list[dict]:
	return [
		{
			"employee": employee,
			"profile": normalize_statutory_profile(frappe.db.get_value("Employee", employee, STATUTORY_PROFILE_FIELD)),
			"issues": employee_readiness(employee, doc.company, doc.end_date),
			"notes": _wage_basis_notes(employee, doc.end_date),
		}
		for employee in _employee_names(doc)
	]


def _stale_profile_slips(payroll_entry: str) -> list[str]:
	"""Find draft Salary Slips whose saved profile no longer matches Employee."""
	rows = frappe.get_all(
		"Salary Slip",
		filters={"payroll_entry": payroll_entry, "docstatus": 0},
		fields=["name", "employee", STATUTORY_PROFILE_FIELD],
	)
	stale = []
	for row in rows:
		current = employee_statutory_profile(row.employee)
		if normalize_statutory_profile(row.get(STATUTORY_PROFILE_FIELD)) != current:
			stale.append(row.name)
	return stale


def validate_payroll_release(doc, method=None):
	if not frappe.db.get_value("Company", doc.company, "custom_enable_malaysia_payroll"):
		return
	company_issues = hrd_registration_issues(doc.company, doc.end_date) + missing_component_account_issues(doc.company)
	if company_issues:
		frappe.throw(_("Resolve the Company statutory setup before submitting this Payroll Entry:<br>{0}").format("<br>".join(company_issues)))
	stale_slips = _stale_profile_slips(doc.name)
	if stale_slips:
		frappe.throw(
			_("These draft Salary Slips use an older Statutory Profile. Open and save them again before submitting Payroll Entry: {0}.").format(
				", ".join(stale_slips)
			)
		)
	blocked = [row for row in readiness(doc) if row["issues"]]
	if blocked:
		details = "<br>".join(
			f"<b>{frappe.utils.escape_html(row['employee'])}</b>: "
			+ frappe.utils.escape_html(" ".join(row["issues"]))
			for row in blocked
		)
		frappe.throw(_("Resolve the statutory setup issues before submitting this Payroll Entry:<br>{0}").format(details))
	if not frappe.db.get_single_value("Payroll Settings", "include_holidays_in_total_working_days"):
		frappe.throw(
			_("Enable 'Include holidays in Total no. of Working Days' in Payroll Settings for calendar-day incomplete-month calculations.")
		)
	assert_rule_pack_covers(doc.end_date)


@frappe.whitelist()
def check_readiness(payroll_entry: str) -> dict:
	doc = frappe.get_doc("Payroll Entry", payroll_entry)
	doc.check_permission("read")
	rows = readiness(doc)
	company_issues = hrd_registration_issues(doc.company, doc.end_date) + missing_component_account_issues(doc.company)
	return {
		"status": "Needs Attention" if company_issues or any(row["issues"] for row in rows) else ("Ready" if rows else "No Employees"),
		"company_issues": company_issues,
		"employees": rows,
	}

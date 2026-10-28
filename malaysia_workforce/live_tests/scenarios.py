from __future__ import annotations

import platform
from datetime import date, timedelta
from decimal import Decimal

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils.password import update_password

from malaysia_workforce.payroll.events import check_readiness

COMPANY = "MW Lean Cafe Sdn Bhd"
EMPLOYEE_USER = "aina.lean@example.com"
PAYROLL_OWNER = "payroll.owner@example.com"
PAYROLL_RELEASER = "payroll.releaser@example.com"
HR_MANAGER = "hr.manager@example.com"
AUDITOR = "payroll.auditor@example.com"
SYSTEM_MANAGER = "system.manager@example.com"
PASSWORD = "Malaysia-Payroll-E2E-2026"
PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)
JUNE_START = date(2026, 6, 1)
JUNE_END = date(2026, 6, 30)
CONTRACTOR_NUMBER = "MWL0000002"


def runtime_info() -> dict:
	from frappe.model.base_document import get_controller
	from malaysia_workforce.payroll.overtime import MalaysiaOvertimeMixin

	obsolete = (
		"Casual Availability", "Cafe Staffing Plan", "Malaysia Payroll Run",
		"Malaysia Employee Profile", "Employee Work Agreement", "Shift Work Record",
	)
	return {
		"database": frappe.db.sql("select version()", pluck=True)[0],
		"python": platform.python_version(),
		"apps": {row.app_name: row.app_version for row in frappe.get_all(
			"Installed Application", fields=["app_name", "app_version"]
		)},
		"obsolete_doctypes_present": [name for name in obsolete if frappe.db.exists("DocType", name)],
		"overtime_extension_loaded": MalaysiaOvertimeMixin in get_controller("Overtime Slip").__mro__,
	}


def database_grants() -> list[str]:
	return [row[0] for row in frappe.db.sql("show grants")]


def auditor_permission_debug() -> dict:
	from frappe.permissions import get_doc_permissions
	from malaysia_workforce.permissions import employee_tax_permission, tp1_query

	name = frappe.db.get_value("Malaysia Tax Declaration TP1", {"company": COMPANY}, "name")
	doc = frappe.get_doc("Malaysia Tax Declaration TP1", name)
	frappe.set_user(AUDITOR)
	result = {
		"roles": frappe.get_roles(AUDITOR),
		"user_permissions": frappe.get_all("User Permission", filters={"user": AUDITOR},
			fields=["allow", "for_value", "applicable_for"]),
		"doctype_read": frappe.has_permission(doc.doctype, "read", user=AUDITOR),
		"hook_read": employee_tax_permission(doc, user=AUDITOR, permission_type="read"),
		"query": tp1_query(AUDITOR),
		"document_permissions": get_doc_permissions(doc, user=AUDITOR),
	}
	frappe.set_user("Administrator")
	return result


def _mark_setup_complete() -> None:
	for app in ("frappe", "erpnext"):
		for name in frappe.get_all("Installed Application", filters={"app_name": app}, pluck="name"):
			frappe.db.set_value("Installed Application", name, "is_setup_complete", 1, update_modified=False)
	frappe.db.set_single_value("System Settings", "setup_complete", 1)
	frappe.db.set_single_value("System Settings", "time_zone", "Asia/Kuala_Lumpur")
	frappe.db.set_single_value("Global Defaults", "country", "Malaysia")
	frappe.db.set_single_value("Global Defaults", "default_currency", "MYR")
	frappe.db.set_single_value("Payroll Settings", "include_holidays_in_total_working_days", 1)
	frappe.defaults.set_global_default("country", "Malaysia")
	frappe.defaults.set_global_default("currency", "MYR")
	frappe.defaults.set_global_default("time_zone", "Asia/Kuala_Lumpur")


def _user(email: str, first_name: str, roles: tuple[str, ...]) -> str:
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": first_name,
			"enabled": 1, "send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}).insert(ignore_permissions=True)
	else:
		doc = frappe.get_doc("User", email)
		existing = {row.role for row in doc.roles}
		for role in roles:
			if role not in existing:
				doc.append("roles", {"role": role})
		doc.save(ignore_permissions=True)
	update_password(email, PASSWORD)
	return email


def _make_employee_self_service_user(email: str) -> None:
	"""Use the native HRMS mobile/PWA user type after Employee is linked."""
	user = frappe.get_doc("User", email)
	if user.user_type != "Employee Self Service":
		user.user_type = "Employee Self Service"
		user.save(ignore_permissions=True)


def _company_permission(user: str) -> None:
	if not frappe.db.exists("User Permission", {"user": user, "allow": "Company", "for_value": COMPANY}):
		frappe.get_doc({
			"doctype": "User Permission", "user": user, "allow": "Company",
			"for_value": COMPANY, "apply_to_all_doctypes": 1,
		}).insert(ignore_permissions=True)


def _private_file(file_name: str, content: str) -> str:
	url = frappe.db.get_value("File", {"file_name": file_name, "is_private": 1}, "file_url")
	if url:
		return url
	return frappe.get_doc({
		"doctype": "File", "file_name": file_name, "content": content, "is_private": 1,
	}).save(ignore_permissions=True).file_url


def _company() -> str:
	if not frappe.db.exists("Warehouse Type", "Transit"):
		frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Company", COMPANY):
		frappe.get_doc({
			"doctype": "Company", "company_name": COMPANY, "abbr": "MWL",
			"country": "Malaysia", "default_currency": "MYR", "chart_of_accounts": "Standard",
		}).insert(ignore_permissions=True)
	frappe.db.set_value("Company", COMPANY, {
		"custom_enable_malaysia_payroll": 1,
		"custom_malaysia_jurisdiction": "Peninsular Malaysia",
		"tax_id": "C25845632020",
		"custom_company_registration_number": "202601012345",
		"custom_lhdn_hq_number": "01",
		"custom_lhdn_employer_number": "E1234567800",
		"custom_epf_employer_number": "12345678",
		"custom_socso_employer_code": "A1234567890",
		"custom_hrd_registration_class": "Compulsory (1%)",
		"custom_hrd_registration_number": "HRD-MWL-2026",
		"custom_hrd_effective_from": "2026-01-01",
	}, update_modified=False)
	frappe.clear_cache(doctype="Company")
	return COMPANY


def _holiday_setup() -> str:
	name = "MW Lean Malaysia 2026"
	if not frappe.db.exists("Holiday List", name):
		frappe.get_doc({
			"doctype": "Holiday List", "holiday_list_name": name,
			"from_date": "2026-01-01", "to_date": "2026-12-31", "country": "Malaysia",
		}).insert(ignore_permissions=True)
	frappe.db.set_value("Company", COMPANY, "default_holiday_list", name, update_modified=False)
	if not frappe.db.exists("Holiday List Assignment", {
		"holiday_list": name, "applicable_for": "Company", "assigned_to": COMPANY, "docstatus": 1,
	}):
		assignment = frappe.get_doc({
			"doctype": "Holiday List Assignment", "naming_series": "HR-HLA-.YYYY.-",
			"holiday_list": name, "applicable_for": "Company", "assigned_to": COMPANY,
			"from_date": "2026-01-01",
		}).insert(ignore_permissions=True)
		assignment.submit()
	frappe.clear_cache(doctype="Company")
	return name


def _fiscal_year_setup() -> str:
	name = "2026"
	if frappe.db.exists("Fiscal Year", name):
		doc = frappe.get_doc("Fiscal Year", name)
		if COMPANY not in {row.company for row in doc.companies}:
			doc.append("companies", {"company": COMPANY})
			doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({
			"doctype": "Fiscal Year", "year": name,
			"year_start_date": "2026-01-01", "year_end_date": "2026-12-31",
			"companies": [{"company": COMPANY}],
		}).insert(ignore_permissions=True)
	return name


def _payroll_period_setup() -> str:
	name = "MW Lean Payroll 2026"
	if not frappe.db.exists("Payroll Period", name):
		frappe.get_doc({
			"doctype": "Payroll Period",
			"name": name,
			"company": COMPANY,
			"start_date": "2026-01-01",
			"end_date": "2026-12-31",
		}).insert(ignore_permissions=True)
	return name


def _employee() -> str:
	if not frappe.db.exists("Gender", "Female"):
		frappe.get_doc({"doctype": "Gender", "gender": "Female"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Designation", "Barista"):
		frappe.get_doc({"doctype": "Designation", "designation_name": "Barista"}).insert(ignore_permissions=True)
	employee = frappe.db.get_value("Employee", {"user_id": EMPLOYEE_USER}, "name")
	values = {
		"first_name": "Aina", "last_name": "Rahman", "employee_number": "MWL0000001",
		"company": COMPANY, "designation": "Barista", "gender": "Female",
		"date_of_birth": "1998-04-15", "date_of_joining": "2026-01-01",
		"status": "Active", "user_id": EMPLOYEE_USER, "bank_ac_no": "123456789012",
		"custom_malaysia_citizenship_status": "Malaysian Citizen",
		"custom_nric": "980415140001", "custom_tax_identification_number": "IG123456780",
		"custom_epf_member_number": "10000001",
		"custom_socso_category": "First", "custom_eis_eligible": 1,
		# The common case: LINDUNG 24 Jam participation is the statutory default,
		# so a real employee has no paperwork on file at all. Explicit None keeps
		# doc.update() from carrying stale values on a re-run.
		"custom_lindung_participation": "Participating",
		"custom_lindung_registration_date": None,
		"custom_lindung_effective_from": None,
		"custom_lindung_evidence": None,
		"custom_lindung_multiple_employers": 0,
		"custom_pcb_resident": 1, "custom_pcb_category": "1 - Single", "custom_pcb_child_units": 0,
	}
	if employee:
		doc = frappe.get_doc("Employee", employee)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Employee", **values}).insert(ignore_permissions=True)
		employee = doc.name
	return employee


def _contract(employee: str) -> str:
	name = frappe.db.get_value("Contract", {
		"party_type": "Employee", "party_name": employee, "docstatus": 1,
	}, "name")
	if name:
		return name
	doc = frappe.get_doc({
		"doctype": "Contract", "party_type": "Employee", "party_name": employee,
		"is_signed": 1, "start_date": "2026-01-01", "contract_terms": "Standard Malaysian employment terms.",
		"custom_malaysia_wage_basis": "Monthly", "custom_malaysia_work_classification": "Full-time",
		"custom_contract_wage_rate": 5000, "custom_normal_hours_per_day": 8,
		"custom_normal_hours_per_week": 45, "custom_rest_day": "Sunday", "custom_overtime_eligible": 1,
	}).insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _accounts() -> tuple[str, str]:
	payable = frappe.db.get_value("Account", {
		"company": COMPANY, "account_type": "Payable", "root_type": "Liability", "is_group": 0,
	}, "name")
	expense = frappe.db.get_value("Account", {
		"company": COMPANY, "root_type": "Expense", "is_group": 0,
	}, "name")
	if not payable or not expense:
		frappe.throw("The isolated company does not have the required payable and expense accounts.")
	return payable, expense


def _salary_component(name: str, abbr: str, *, treatment: str, expense: str) -> None:
	if not frappe.db.exists("Salary Component", name):
		doc = frappe.get_doc({
			"doctype": "Salary Component", "salary_component": name,
			"salary_component_abbr": abbr, "type": "Earning", "depends_on_payment_days": 0,
			"custom_include_in_epf_wages": 1, "custom_include_in_socso_wages": 1,
			"custom_include_in_eis_wages": 1, "custom_include_in_hrd_levy_wages": 1,
			"custom_pcb_treatment": treatment,
			"custom_include_in_ordinary_rate": int(treatment == "Regular Remuneration"),
		}).insert(ignore_permissions=True)
	else:
		doc = frappe.get_doc("Salary Component", name)
	if COMPANY not in {row.company for row in doc.accounts}:
		doc.append("accounts", {"company": COMPANY, "account": expense})
		doc.save(ignore_permissions=True)


def _payroll_setup(employee: str) -> tuple[str, str]:
	payable, expense = _accounts()
	_salary_component("MW Lean Basic Pay", "MWLB", treatment="Regular Remuneration", expense=expense)
	_salary_component("MW Lean Bonus", "MWBN", treatment="Additional Remuneration", expense=expense)
	for component in ("EPF Employee", "SOCSO Employee", "SKBBK Employee", "EIS Employee", "PCB", "CP38", "Zakat"):
		doc = frappe.get_doc("Salary Component", component)
		account = expense if doc.type == "Earning" else payable
		if COMPANY not in {row.company for row in doc.accounts}:
			doc.append("accounts", {"company": COMPANY, "account": account})
			doc.save(ignore_permissions=True)
	structure_name = "MW Lean Monthly Salary"
	if not frappe.db.exists("Salary Structure", structure_name):
		structure = frappe.get_doc({
			"doctype": "Salary Structure", "name": structure_name, "company": COMPANY,
			"is_active": "Yes", "payroll_frequency": "Monthly", "currency": "MYR",
			"earnings": [{"salary_component": "MW Lean Basic Pay", "amount": 5000}],
			"deductions": [{"salary_component": "Zakat", "amount": 100}],
		}).insert(ignore_permissions=True)
		structure.submit()
	if not frappe.db.exists("Salary Structure Assignment", {
		"employee": employee, "salary_structure": structure_name, "docstatus": 1,
	}):
		assignment = frappe.get_doc({
			"doctype": "Salary Structure Assignment", "employee": employee,
			"salary_structure": structure_name, "company": COMPANY, "from_date": "2026-01-01",
			"base": 5000, "currency": "MYR", "payroll_payable_account": payable,
		}).insert(ignore_permissions=True)
		assignment.submit()
	if not frappe.db.exists("Additional Salary", {
		"employee": employee, "salary_component": "MW Lean Bonus", "payroll_date": PERIOD_END, "docstatus": 1,
	}):
		additional = frappe.get_doc({
			"doctype": "Additional Salary", "employee": employee, "company": COMPANY,
			"salary_component": "MW Lean Bonus", "amount": 1000, "payroll_date": PERIOD_END,
		}).insert(ignore_permissions=True)
		additional.submit()
	_overtime_setup(expense)
	return structure_name, payable


def _overtime_setup(expense: str) -> None:
	"""Configure ordinary HRMS masters; the app adds only the statutory day type."""
	_salary_component("Cafe Overtime Pay", "CFOT", treatment="Additional Remuneration", expense=expense)
	frappe.db.set_value(
		"Salary Component",
		"Cafe Overtime Pay",
		{"custom_include_in_epf_wages": 0, "custom_include_in_ordinary_rate": 0},
		update_modified=False,
	)
	if not frappe.db.exists("Overtime Type", "Cafe Normal Overtime"):
		frappe.get_doc(
			{
				"doctype": "Overtime Type",
				"name": "Cafe Normal Overtime",
				"overtime_salary_component": "Cafe Overtime Pay",
				"overtime_calculation_method": "Fixed Hourly Rate",
				"hourly_rate": 1,
				"standard_multiplier": 1,
				"maximum_overtime_hours_allowed": 8,
				"custom_malaysia_pay_type": "Normal Overtime",
			}
		).insert(ignore_permissions=True)


def _employee_declarations(employee: str) -> dict:
	receipt = _private_file("mw-lean-tp1-receipt.txt", "Synthetic receipt for isolated payroll testing")
	tp3_evidence = _private_file("mw-lean-tp3-signed.txt", "Synthetic signed TP3 for isolated payroll testing")
	if not frappe.db.exists("Malaysia Tax Declaration TP1", {"employee": employee, "tax_year": 2026}):
		frappe.set_user(EMPLOYEE_USER)
		tp1 = frappe.get_doc({
			"doctype": "Malaysia Tax Declaration TP1", "employee": employee, "company": COMPANY,
			"tax_year": 2026, "declaration_date": "2026-07-01",
			"employee_declaration": 1,
			"relief_claims": [{"relief_code": "C5", "amount": 500, "claim_month": 7,
				"evidence_reference": receipt}],
		}).insert()
		apply_workflow(tp1, "Send for Review")
		frappe.set_user(HR_MANAGER)
		apply_workflow(frappe.get_doc(tp1.doctype, tp1.name), "Approve")
	if not frappe.db.exists("Malaysia Previous Employment TP3", {"employee": employee, "tax_year": 2026}):
		frappe.set_user(EMPLOYEE_USER)
		tp3 = frappe.get_doc({
			"doctype": "Malaysia Previous Employment TP3", "employee": employee, "company": COMPANY,
			"tax_year": 2026, "previous_employer_name": "Previous Cafe Sdn Bhd",
			"employment_start": "2026-01-01", "employment_end": "2026-01-31",
			"gross_normal_remuneration": 3000, "epf_contribution": 330, "mtd_paid": 25,
			"zakat_paid": 50, "optional_reliefs": 0, "evidence": tp3_evidence,
			"employee_declaration": 1,
		}).insert()
		apply_workflow(tp3, "Send for Review")
		frappe.set_user(HR_MANAGER)
		apply_workflow(frappe.get_doc(tp3.doctype, tp3.name), "Approve")
	if not frappe.db.exists("Malaysia CP38 Directive", {"directive_reference": "CP38-MW-LEAN-001"}):
		frappe.set_user(HR_MANAGER)
		directive = frappe.get_doc({
			"doctype": "Malaysia CP38 Directive", "employee": employee, "company": COMPANY,
			"directive_reference": "CP38-MW-LEAN-001", "effective_from": "2026-07-01",
			"directive_amount": 300, "monthly_deduction": 100,
			"evidence": _private_file("mw-lean-cp38.txt", "Synthetic LHDN CP38 directive"),
		}).insert()
		directive.submit()
	frappe.set_user("Administrator")
	return {"tp1_receipt": receipt, "tp3_evidence": tp3_evidence}


def seed_browser_site(*, commit: bool = True) -> dict:
	frappe.set_user("Administrator")
	_mark_setup_complete()
	_company()
	_fiscal_year_setup()
	_payroll_period_setup()
	_holiday_setup()
	_user(EMPLOYEE_USER, "Aina", ("Employee",))
	_user(HR_MANAGER, "Maya", ("HR Manager", "HR User"))
	_user(PAYROLL_OWNER, "Priya", ("HR Manager", "Accounts User"))
	_user(PAYROLL_RELEASER, "Hana", ("HR Manager", "Accounts Manager"))
	_user(AUDITOR, "Adam", ("Auditor",))
	# ERPNext's Company dashboard reads accounting links such as Sales Invoice.
	# Give the isolated setup administrator Accounts Manager so clicking the
	# standard Company form does not raise an unrelated dashboard permission dialog.
	_user(SYSTEM_MANAGER, "Sam", ("System Manager", "Accounts Manager"))
	for user in (HR_MANAGER, PAYROLL_OWNER, PAYROLL_RELEASER, AUDITOR):
		_company_permission(user)
	for user in (HR_MANAGER, PAYROLL_OWNER, PAYROLL_RELEASER, AUDITOR, SYSTEM_MANAGER):
		frappe.defaults.set_user_default("Company", COMPANY, user)
	employee = _employee()
	_make_employee_self_service_user(EMPLOYEE_USER)
	_contract(employee)
	_payroll_setup(employee)
	_employee_declarations(employee)
	if commit:
		frappe.db.commit()
	return {
		"company": COMPANY, "employee": employee, "password": PASSWORD,
		"users": {"employee": EMPLOYEE_USER, "hr_manager": HR_MANAGER,
			"payroll_owner": PAYROLL_OWNER, "payroll_releaser": PAYROLL_RELEASER,
			"auditor": AUDITOR, "system_manager": SYSTEM_MANAGER},
	}


def _payroll_entry(employee: str, payable: str, start_date=PERIOD_START, end_date=PERIOD_END):
	name = frappe.db.get_value("Payroll Entry", {
		"company": COMPANY, "start_date": start_date, "end_date": end_date, "docstatus": ["<", 2],
	}, "name")
	if name:
		return frappe.get_doc("Payroll Entry", name)
	frappe.set_user(PAYROLL_OWNER)
	entry = frappe.get_doc({
		"doctype": "Payroll Entry", "company": COMPANY, "posting_date": end_date,
		"payroll_frequency": "Monthly", "start_date": start_date, "end_date": end_date,
		"currency": "MYR", "exchange_rate": 1, "payroll_payable_account": payable,
		"cost_center": frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 0}, "name"),
	}).insert()
	entry.fill_employee_details()
	entry.employees = [row for row in entry.employees if row.employee == employee]
	entry.save()
	return entry


def _exercise_overtime(employee: str) -> dict:
	name = frappe.db.get_value("Overtime Slip", {
		"employee": employee, "start_date": "2026-08-01", "end_date": "2026-08-31", "docstatus": 1,
	}, "name")
	if name:
		doc = frappe.get_doc("Overtime Slip", name)
	else:
		frappe.set_user(HR_MANAGER)
		doc = frappe.get_doc({
			"doctype": "Overtime Slip", "posting_date": "2026-08-31", "employee": employee,
			"company": COMPANY, "start_date": "2026-08-01", "end_date": "2026-08-31",
			"total_overtime_duration": 2,
			"overtime_details": [{"date": "2026-08-01", "overtime_type": "Cafe Normal Overtime",
				"overtime_duration": 2, "standard_working_hours": 8}],
		}).insert()
		doc.submit()
	additional = frappe.db.get_value("Additional Salary", {
		"ref_doctype": "Overtime Slip", "ref_docname": doc.name, "docstatus": 1,
	}, ["name", "amount"], as_dict=True)
	return {"overtime_slip": doc.name, "additional_salary": additional.name, "amount": additional.amount}


def _exercise_part_time_overtime(employee: str) -> dict:
	"""Exercise the HRMS extension across the two Regulation 5 pay bands."""
	name = frappe.db.get_value("Overtime Slip", {
		"employee": employee, "start_date": "2026-10-01", "end_date": "2026-10-31", "docstatus": 1,
	}, "name")
	if name:
		doc = frappe.get_doc("Overtime Slip", name)
	else:
		contract_name = frappe.db.get_value("Contract", {
			"party_type": "Employee", "party_name": employee, "docstatus": 1,
		}, "name", order_by="start_date desc")
		fields = (
			"custom_malaysia_wage_basis", "custom_malaysia_work_classification", "custom_contract_wage_rate",
			"custom_normal_hours_per_day", "custom_normal_hours_per_week",
			"custom_comparable_full_time_hours_per_day", "custom_comparable_full_time_hours",
		)
		original = frappe.db.get_value("Contract", contract_name, list(fields), as_dict=True)
		try:
			frappe.db.set_value("Contract", contract_name, {
				"custom_malaysia_wage_basis": "Hourly", "custom_malaysia_work_classification": "Part-time",
				"custom_contract_wage_rate": 10, "custom_normal_hours_per_day": 4,
				"custom_normal_hours_per_week": 20, "custom_comparable_full_time_hours_per_day": 8,
				"custom_comparable_full_time_hours": 45,
			}, update_modified=False)
			frappe.set_user(HR_MANAGER)
			doc = frappe.get_doc({
				"doctype": "Overtime Slip", "posting_date": "2026-10-31", "employee": employee,
				"company": COMPANY, "start_date": "2026-10-01", "end_date": "2026-10-31",
				"total_overtime_duration": 6,
				"overtime_details": [{"date": "2026-10-01", "overtime_type": "Cafe Normal Overtime",
					"overtime_duration": 6, "standard_working_hours": 4}],
			}).insert()
			doc.submit()
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Contract", contract_name, dict(original), update_modified=False)
	additional = frappe.db.get_value("Additional Salary", {
		"ref_doctype": "Overtime Slip", "ref_docname": doc.name, "docstatus": 1,
	}, ["name", "amount"], as_dict=True)
	if float(additional.amount) != 70:
		frappe.throw(f"Expected RM 70.00 part-time additional work pay, found RM {additional.amount}.")
	return {"overtime_slip": doc.name, "additional_salary": additional.name, "amount": additional.amount}


def _filings() -> dict:
	frappe.set_user(PAYROLL_RELEASER)
	results = {}
	for authority in ("EPF", "PERKESO", "LHDN", "HRD Corp"):
		name = frappe.db.get_value("Malaysia Statutory Filing", {
			"company": COMPANY, "authority": authority,
			"period_start": PERIOD_START, "period_end": PERIOD_END, "docstatus": ["<", 2],
		}, "name")
		if name:
			doc = frappe.get_doc("Malaysia Statutory Filing", name)
		else:
			doc = frappe.get_doc({
				"doctype": "Malaysia Statutory Filing", "company": COMPANY, "authority": authority,
				"period_start": PERIOD_START, "period_end": PERIOD_END,
			}).insert()
		if doc.docstatus == 0:
			doc.prepare()
			doc.reload()
		results[authority] = {"name": doc.name, "docstatus": doc.docstatus, "file": doc.generated_file,
			"file_hash": doc.file_hash, "employees": len(doc.employee_lines)}

	# Exercise native submission plus the small external-authority acknowledgement state on EPF.
	epf = frappe.get_doc("Malaysia Statutory Filing", results["EPF"]["name"])
	if epf.docstatus == 0:
		epf.submission_evidence = _private_file("mw-lean-epf-portal-receipt.txt", "Synthetic EPF portal receipt")
		epf.save()
		epf.submit()
	if epf.docstatus == 1 and epf.reconciliation_status != "Reconciled":
		epf.authority_status = "Accepted"
		epf.acknowledgement = _private_file("mw-lean-epf-ack.txt", "Synthetic EPF acknowledgement")
		epf.save()
		epf.reconcile()
	epf.reload()
	results["EPF"].update(
		{"docstatus": epf.docstatus, "authority_status": epf.authority_status,
		 "reconciliation_status": epf.reconciliation_status}
	)
	frappe.set_user("Administrator")
	return results


def _permission_evidence(tp1: str, filing: str) -> dict:
	out = {}
	tp1_doc = frappe.get_doc("Malaysia Tax Declaration TP1", tp1)
	filing_doc = frappe.get_doc("Malaysia Statutory Filing", filing)
	for user in (EMPLOYEE_USER, HR_MANAGER, PAYROLL_OWNER, PAYROLL_RELEASER, AUDITOR):
		frappe.set_user(user)
		out[user] = {
			"tp1_read": bool(frappe.has_permission("Malaysia Tax Declaration TP1", "read", doc=tp1_doc, user=user)),
			"tp1_write": bool(frappe.has_permission("Malaysia Tax Declaration TP1", "write", doc=tp1_doc, user=user)),
			"filing_read": bool(frappe.has_permission("Malaysia Statutory Filing", "read", doc=filing_doc, user=user)),
			"filing_write": bool(frappe.has_permission("Malaysia Statutory Filing", "write", doc=filing_doc, user=user)),
		}
	frappe.set_user("Administrator")
	return out


def run_all(*, commit: bool = True) -> dict:
	seed = seed_browser_site(commit=True)
	employee = seed["employee"]
	payable, _ = _accounts()
	entry = _payroll_entry(employee, payable)
	readiness = check_readiness(entry.name)
	entry.reload()
	# Payroll Entry submission is a separate native request in Desk. Commit the
	# draft first because HRMS deliberately rolls back a failed slip batch.
	frappe.db.commit()
	if entry.docstatus == 0:
		entry.submit()
	entry.reload()
	if frappe.db.exists("Salary Slip", {"payroll_entry": entry.name, "docstatus": 0}):
		entry.submit_salary_slips()
	entry.reload()
	slips = frappe.get_all("Salary Slip", filters={"payroll_entry": entry.name, "docstatus": 1}, pluck="name")
	if len(slips) != 1:
		frappe.throw(f"Expected one submitted Salary Slip, found {len(slips)}.")
	slip = frappe.get_doc("Salary Slip", slips[0])
	result_rows = {row.scheme: {"employee": row.employee_amount, "employer": row.employer_amount,
		"extra": row.extra_employee_amount, "wages": row.wage_base} for row in slip.custom_malaysia_statutory_results}

	frappe.set_user("Administrator")
	filings = _filings()
	overtime = _exercise_overtime(employee)
	part_time_overtime = _exercise_part_time_overtime(employee)
	tp1 = frappe.db.get_value("Malaysia Tax Declaration TP1", {"employee": employee, "docstatus": 1})
	# Employee access follows the linked Employee, not whichever user happened
	# to create the declaration on their behalf.
	frappe.db.set_value("Malaysia Tax Declaration TP1", tp1, "owner", HR_MANAGER, update_modified=False)
	permission_evidence = _permission_evidence(tp1, filings["EPF"]["name"])
	from malaysia_workforce.malaysia_workforce.report.malaysia_annual_remuneration.malaysia_annual_remuneration import execute as annual_report
	from malaysia_workforce.malaysia_workforce.report.malaysia_payroll_readiness.malaysia_payroll_readiness import execute as readiness_report
	annual_columns, annual_rows = annual_report({"company": COMPANY, "year": 2026})
	ready_columns, ready_rows = readiness_report({"company": COMPANY, "payroll_date": PERIOD_END})
	frappe.set_user("Administrator")
	result = {
		"runtime": runtime_info(), "seed": seed,
		"payroll": {"entry": entry.name, "readiness": readiness["status"], "salary_slip": slip.name,
			"gross_pay": slip.gross_pay, "net_pay": slip.net_pay,
			"statutory": result_rows, "payroll_entry_docstatus": entry.docstatus,
			"salary_slip_docstatus": slip.docstatus},
		"overtime": overtime, "part_time_overtime": part_time_overtime,
		"filings": filings, "permissions": permission_evidence,
		"reports": {"annual_rows": len(annual_rows), "annual_columns": len(annual_columns),
			"readiness_rows": len(ready_rows), "readiness_columns": len(ready_columns)},
	}
	if commit:
		frappe.db.commit()
	return result


def run_source_tamper(*, commit: bool = True) -> dict:
	"""Prove filing controls detect changed calculations and serialized identities."""
	run_all(commit=True)
	filing_name = frappe.db.get_value(
		"Malaysia Statutory Filing",
		{"company": COMPANY, "authority": "PERKESO", "period_start": PERIOD_START,
		 "period_end": PERIOD_END, "docstatus": 0},
		"name",
	)
	filing = frappe.get_doc("Malaysia Statutory Filing", filing_name)
	frappe.set_user(PAYROLL_RELEASER)
	first = filing.prepare()
	filing.reload()
	second = filing.prepare()
	slip_names = frappe.get_all(
		"Salary Slip",
		filters={"company": COMPANY, "docstatus": 1, "end_date": ["between", [PERIOD_START, PERIOD_END]]},
		pluck="name",
	)
	result_name = frappe.db.get_value(
		"Malaysia Statutory Result",
		{"parenttype": "Salary Slip", "parent": ["in", slip_names], "scheme": "SOCSO"},
		"name",
		order_by="modified desc",
	)
	original = frappe.db.get_value("Malaysia Statutory Result", result_name, "employee_amount")
	blocked = False
	try:
		frappe.db.set_value("Malaysia Statutory Result", result_name, "employee_amount", float(original or 0) + 0.01,
			update_modified=False)
		try:
			from malaysia_workforce.statutory.filing import validate_filing_source

			validate_filing_source(filing)
		except frappe.ValidationError:
			blocked = True
		if not blocked:
			frappe.throw("The filing source change was not detected.")
	finally:
		frappe.db.set_value("Malaysia Statutory Result", result_name, "employee_amount", original,
			update_modified=False)
	employee = filing.employee_lines[0].employee
	original_nric = frappe.db.get_value("Employee", employee, "custom_nric")
	identity_blocked = False
	try:
		changed_nric = f"{str(original_nric)[:-1]}{'0' if str(original_nric)[-1] != '0' else '1'}"
		frappe.db.set_value("Employee", employee, "custom_nric", changed_nric, update_modified=False)
		try:
			validate_filing_source(filing)
		except frappe.ValidationError:
			identity_blocked = True
		if not identity_blocked:
			frappe.throw("A serialized employee identity change was not detected.")
	finally:
		frappe.db.set_value("Employee", employee, "custom_nric", original_nric, update_modified=False)
	frappe.set_user("Administrator")
	result = {
		"filing": filing.name,
		"same_artifact_on_retry": first["file"] == second["file"] and first["source_hash"] == second["source_hash"],
		"changed_source_detected": blocked,
		"changed_identity_detected": identity_blocked,
	}
	if commit:
		frappe.db.commit()
	return result


def run_report_permission_isolation(*, commit: bool = True) -> dict:
	"""Prove report filters cannot bypass Company User Permissions."""
	seed_browser_site(commit=True)
	other_company = frappe.db.get_value("Company", {"name": ["!=", COMPANY]}, "name")
	if not other_company:
		other_company = frappe.get_doc({
			"doctype": "Company",
			"company_name": "MW Isolation Cafe Sdn Bhd",
			"abbr": "MWI",
			"country": "Malaysia",
			"default_currency": "MYR",
			"chart_of_accounts": "Standard",
		}).insert(ignore_permissions=True).name
		frappe.db.commit()
	from malaysia_workforce.malaysia_workforce.report.malaysia_annual_remuneration.malaysia_annual_remuneration import execute as annual_report
	from malaysia_workforce.malaysia_workforce.report.malaysia_payroll_readiness.malaysia_payroll_readiness import execute as readiness_report

	blocked = {}
	frappe.set_user(HR_MANAGER)
	try:
		for name, report, filters in (
			("annual", annual_report, {"company": other_company, "year": 2026}),
			("readiness", readiness_report, {"company": other_company, "payroll_date": PERIOD_END}),
		):
			try:
				report(filters)
			except frappe.PermissionError:
				blocked[name] = True
			else:
				blocked[name] = False
		if not all(blocked.values()):
			frappe.throw(f"Company report isolation failed: {blocked}")
	finally:
		frappe.set_user("Administrator")
	if commit:
		frappe.db.commit()
	return {"user": HR_MANAGER, "other_company": other_company, "blocked": blocked}


def run_overtime_monthly_limit(*, commit: bool = True) -> dict:
	"""Prove non-overlapping slips still share the calendar-month ceiling."""
	seed = seed_browser_site(commit=True)
	frappe.set_user(HR_MANAGER)
	first = None
	blocked = False
	try:
		first_start = date(2026, 11, 2)
		first = frappe.get_doc({
			"doctype": "Overtime Slip",
			"posting_date": "2026-11-11",
			"employee": seed["employee"],
			"company": COMPANY,
			"start_date": first_start,
			"end_date": date(2026, 11, 11),
			"total_overtime_duration": 60,
			"overtime_details": [
				{"date": first_start + timedelta(days=index), "overtime_type": "Cafe Normal Overtime",
				 "overtime_duration": 6, "standard_working_hours": 8}
				for index in range(10)
			],
		}).insert()
		second_start = date(2026, 11, 20)
		try:
			frappe.get_doc({
				"doctype": "Overtime Slip",
				"posting_date": "2026-11-27",
				"employee": seed["employee"],
				"company": COMPANY,
				"start_date": second_start,
				"end_date": date(2026, 11, 27),
				"total_overtime_duration": 48,
				"overtime_details": [
					{"date": second_start + timedelta(days=index), "overtime_type": "Cafe Normal Overtime",
					 "overtime_duration": 6, "standard_working_hours": 8}
					for index in range(8)
				],
			}).insert()
		except frappe.ValidationError:
			frappe.clear_last_message()
			blocked = True
		if not blocked:
			frappe.throw("Non-overlapping Overtime Slips exceeded 104 hours without being blocked.")
	finally:
		frappe.set_user("Administrator")
		if first and frappe.db.exists("Overtime Slip", first.name):
			first.delete(ignore_permissions=True)
	if commit:
		frappe.db.commit()
	return {"employee": seed["employee"], "non_overlapping_same_month_blocked": blocked}


def run_review_guardrails(*, commit: bool = True) -> dict:
	"""Exercise guardrails that do not need a full extra payroll cycle."""
	seed = seed_browser_site(commit=True)
	from malaysia_workforce.payroll.salary_slip import _classify, _cp38_amount
	from malaysia_workforce.payroll.validation import (
		hrd_registration_issues_for_count,
		lindung_payroll_issues,
		lindung_release_issues,
	)

	results = {}
	component_name = "MW Guardrail Unclassified Earning"
	created_component = False
	frappe.set_user("Administrator")
	if not frappe.db.exists("Salary Component", component_name):
		frappe.get_doc({
			"doctype": "Salary Component",
			"salary_component": component_name,
			"type": "Earning",
		}).insert(ignore_permissions=True)
		created_component = True
	try:
		try:
			_classify(frappe._dict(earnings=[frappe._dict(
				salary_component=component_name,
				amount=100,
			)]))
		except frappe.ValidationError as exc:
			frappe.clear_last_message()
			results["blank_earning_treatment_blocked"] = "no Statutory Treatment" in str(exc)
		else:
			results["blank_earning_treatment_blocked"] = False
	finally:
		if created_component:
			frappe.delete_doc("Salary Component", component_name, ignore_permissions=True)

	invalid_release = frappe._dict(
		custom_lindung_participation="Not Participating",
		custom_lindung_registration_date=date(2026, 7, 8),
		custom_lindung_effective_from=date(2026, 7, 12),
		custom_lindung_evidence="/private/files/release.pdf",
	)
	results["invalid_lindung_window_blocked"] = bool(lindung_release_issues(invalid_release))
	invalid_release.custom_lindung_effective_from = date(2026, 7, 13)
	invalid_release.custom_lindung_multiple_employers = 1
	results["multiple_employer_lindung_blocked"] = bool(lindung_payroll_issues(invalid_release))
	results["hrd_headcount_conflict_blocked"] = bool(
		hrd_registration_issues_for_count(
			frappe._dict(custom_hrd_registration_class="Not Registered"),
			10,
			date(2026, 8, 31),
		)
	)
	results["cp38_same_month_balance"] = str(_cp38_amount(
		directive_amount=Decimal("500"),
		monthly_deduction=Decimal("100"),
		total_paid=Decimal("450"),
		already_deducted=Decimal("50"),
	))

	frappe.set_user(HR_MANAGER)
	tp3 = frappe.get_doc({
		"doctype": "Malaysia Previous Employment TP3",
		"employee": seed["employee"],
		"company": COMPANY,
		"tax_year": 2025,
		"previous_employer_name": "Prior Cafe Sdn Bhd",
		"employee_declaration": 1,
	})
	try:
		tp3.before_submit()
	except frappe.ValidationError as exc:
		frappe.clear_last_message()
		results["unsigned_tp3_blocked"] = "signed TP3" in str(exc)
	else:
		results["unsigned_tp3_blocked"] = False
	finally:
		frappe.set_user("Administrator")

	expected = {
		"blank_earning_treatment_blocked": True,
		"invalid_lindung_window_blocked": True,
		"multiple_employer_lindung_blocked": True,
		"hrd_headcount_conflict_blocked": True,
		"cp38_same_month_balance": "50.00",
		"unsigned_tp3_blocked": True,
	}
	if results != expected:
		frappe.throw(f"Review guardrail scenario failed: {results}")
	if commit:
		frappe.db.commit()
	return results


def run_tax_self_service() -> dict:
	"""Prove employee Web Form handoff, retry safety and native HR approval."""
	from malaysia_workforce.permissions import send_tax_declaration_for_review

	seed = seed_browser_site(commit=True)
	try:
		frappe.set_user(EMPLOYEE_USER)
		tp1 = frappe.get_doc({
			"doctype": "Malaysia Tax Declaration TP1",
			"employee": seed["employee"],
			"company": COMPANY,
			"tax_year": 2026,
			"declaration_date": "2026-08-13",
			"employee_declaration": 1,
		}).insert()
		first = send_tax_declaration_for_review(tp1.doctype, tp1.name)
		second = send_tax_declaration_for_review(tp1.doctype, tp1.name)
		if first != second or first["workflow_state"] != "Pending Review":
			frappe.throw(f"Employee TP1 workflow handoff was not retry-safe: {first}, {second}")

		tp3 = frappe.get_doc({
			"doctype": "Malaysia Previous Employment TP3",
			"employee": seed["employee"],
			"company": COMPANY,
			"tax_year": 2026,
			"previous_employer_name": "Second Previous Cafe Sdn Bhd",
			"previous_employer_number": "E8765432100",
			"employment_start": "2026-02-01",
			"employment_end": "2026-02-28",
			"gross_normal_remuneration": 2800,
			"epf_contribution": 308,
			"mtd_paid": 20,
			"evidence": _private_file(
				"mw-lean-second-tp3-signed.txt",
				"Synthetic signed TP3 for a second previous employer",
			),
			"employee_declaration": 1,
		}).insert()
		tp3_result = send_tax_declaration_for_review(tp3.doctype, tp3.name)
		if tp3_result["workflow_state"] != "Pending Review":
			frappe.throw(f"Employee TP3 did not reach Pending Review: {tp3_result}")

		frappe.set_user(HR_MANAGER)
		approved = apply_workflow(frappe.get_doc(tp3.doctype, tp3.name), "Approve")
		if approved.docstatus != 1 or approved.workflow_state != "Approved":
			frappe.throw(f"HR approval did not submit the second TP3: {approved.as_dict()}")
		approved_count = frappe.db.count(
			"Malaysia Previous Employment TP3",
			{"employee": seed["employee"], "tax_year": 2026, "docstatus": 1},
		)
		if approved_count != 2:
			frappe.throw(f"Expected two approved prior employers, found {approved_count}.")
		return {
			"employee": seed["employee"],
			"tp1_state": first["workflow_state"],
			"retry_safe": first == second,
			"tp3_state": approved.workflow_state,
			"approved_previous_employers": approved_count,
		}
	finally:
		# The base browser seed is committed; keep this focused scenario repeatable.
		frappe.db.rollback()
		frappe.set_user("Administrator")


SEPTEMBER_START = date(2026, 9, 1)
SEPTEMBER_END = date(2026, 9, 30)


def _submit_standalone_slip(employee: str, start, end):
	"""Submit one Salary Slip outside a Payroll Entry, as a real off-cycle run does."""
	frappe.set_user("Administrator")
	slip = frappe.get_doc({
		"doctype": "Salary Slip", "employee": employee, "company": COMPANY,
		"payroll_frequency": "Monthly", "start_date": start, "end_date": end, "posting_date": end,
	}).insert(ignore_permissions=True)
	slip.submit()
	slip.reload()
	return slip


def _clear_september_slips(employee: str) -> None:
	frappe.set_user("Administrator")
	for name in frappe.get_all(
		"Salary Slip",
		filters={"employee": employee, "company": COMPANY,
			"start_date": [">=", SEPTEMBER_START], "end_date": ["<=", SEPTEMBER_END]},
		pluck="name",
	):
		doc = frappe.get_doc("Salary Slip", name)
		if doc.docstatus == 1:
			doc.cancel()
		doc.delete()
	frappe.db.commit()


def _slip_amounts(slip) -> dict:
	socso = next(row for row in slip.custom_malaysia_statutory_results if row.scheme == "SOCSO")
	skbbk = [row.amount for row in slip.deductions if row.salary_component == "SKBBK Employee"]
	return {
		"slip": slip.name,
		"skbbk_deduction": skbbk[0] if skbbk else 0,
		"skbbk_result": socso.extra_employee_amount,
		"socso_employee": socso.employee_amount,
		"socso_wage_base": socso.wage_base,
	}


def run_lindung_release(*, commit: bool = True) -> dict:
	"""Prove the LINDUNG 24 Jam opt-out model end to end.

	Two independent properties, both in September 2026 so no Additional Salary,
	Overtime Slip or statutory filing from the other scenarios is disturbed:
	two slips in one month must split the SKBBK band rather than charge it
	twice, and a recorded Liability Release Notice must stop the deduction.
	"""
	from frappe.utils import flt, getdate

	from malaysia_workforce.statutory.calculators.socso import calculate_socso

	seed = seed_browser_site(commit=True)
	employee = seed["employee"]
	_clear_september_slips(employee)

	# 1. Same-month delta: the second slip charges the month band less what the
	#    first already took, never the full band again.
	first = _slip_amounts(_submit_standalone_slip(employee, SEPTEMBER_START, date(2026, 9, 15)))
	second = _slip_amounts(_submit_standalone_slip(employee, date(2026, 9, 16), SEPTEMBER_END))
	month_band = calculate_socso(
		second["socso_wage_base"], "First",
		contribution_date=getdate(SEPTEMBER_END), lindung_participation="Participating",
	).extra_employee
	charged = flt(first["skbbk_deduction"]) + flt(second["skbbk_deduction"])
	if abs(charged - float(month_band)) > 0.005:
		frappe.throw(
			f"SKBBK for September should total RM {month_band} across both slips, found RM {charged:.2f}."
		)
	if flt(second["socso_employee"]) < 0:
		frappe.throw(f"Second slip SOCSO employee amount went negative: {second['socso_employee']}.")
	_clear_september_slips(employee)

	# 2. A recorded release stops the deduction from its effective date.
	fields = (
		"custom_lindung_participation",
		"custom_lindung_registration_date",
		"custom_lindung_effective_from",
		"custom_lindung_evidence",
	)
	original = frappe.db.get_value("Employee", employee, list(fields), as_dict=True)
	try:
		frappe.db.set_value("Employee", employee, {
			"custom_lindung_participation": "Not Participating",
			"custom_lindung_registration_date": "2026-01-01",
			"custom_lindung_effective_from": "2026-07-15",
			"custom_lindung_evidence": _private_file(
				"mw-lean-lindung-release-notice.txt",
				"Synthetic PERKESO Liability Release Notice for isolated payroll testing",
			),
		}, update_modified=False)
		frappe.db.commit()
		released = _slip_amounts(_submit_standalone_slip(employee, SEPTEMBER_START, SEPTEMBER_END))
		if released["skbbk_deduction"] or flt(released["skbbk_result"]) != 0:
			frappe.throw(f"A released employee was still charged SKBBK: {released}.")
	finally:
		_clear_september_slips(employee)
		frappe.db.set_value("Employee", employee, dict(original), update_modified=False)
		frappe.set_user("Administrator")

	result = {
		"same_month_first": first, "same_month_second": second,
		"september_band": str(month_band), "same_month_total_charged": round(charged, 2),
		"released": released,
	}
	if commit:
		frappe.db.commit()
	return result


def seed_chrome_scenarios(*, commit: bool = True) -> dict:
	"""Create deterministic draft/submitted records for role-based UI testing."""
	seed = seed_browser_site(commit=True)
	employee = seed["employee"]
	payable, _ = _accounts()

	draft = _payroll_entry(employee, payable, date(2026, 11, 1), date(2026, 11, 30))
	release_entry = _payroll_entry(employee, payable, date(2026, 12, 1), date(2026, 12, 31))
	if release_entry.docstatus == 0:
		check_readiness(release_entry.name)
		frappe.db.commit()
		release_entry.reload()
		release_entry.submit()
	release_entry.reload()
	if frappe.db.exists("Salary Slip", {"payroll_entry": release_entry.name, "docstatus": 0}):
		release_entry.submit_salary_slips()
	release_entry.reload()

	filing_name = frappe.db.get_value("Malaysia Statutory Filing", {
		"company": COMPANY, "authority": "EPF",
		"period_start": "2026-12-01", "period_end": "2026-12-31", "docstatus": 0,
	}, "name")
	if not filing_name:
		frappe.set_user(PAYROLL_RELEASER)
		filing_name = frappe.get_doc({
			"doctype": "Malaysia Statutory Filing", "company": COMPANY, "authority": "EPF",
			"period_start": "2026-12-01", "period_end": "2026-12-31",
		}).insert().name

	frappe.set_user("Administrator")
	result = {
		"draft_payroll_entry": draft.name,
		"submitted_payroll_entry": release_entry.name,
		"submitted_payroll_docstatus": release_entry.docstatus,
		"draft_filing": filing_name,
	}
	if commit:
		frappe.db.commit()
	return result


def _contractor_employee() -> str:
	from malaysia_workforce.payroll.profile import SOCSO_EIS_LINDUNG_PROFILE

	if not frappe.db.exists("Gender", "Male"):
		frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Designation", "Contractor"):
		frappe.get_doc({"doctype": "Designation", "designation_name": "Contractor"}).insert(ignore_permissions=True)
	employee = frappe.db.get_value("Employee", {"employee_number": CONTRACTOR_NUMBER}, "name")
	values = {
		"first_name": "Hakim", "last_name": "Contractor", "employee_number": CONTRACTOR_NUMBER,
		"company": COMPANY, "designation": "Contractor", "gender": "Male",
		"date_of_birth": "1995-08-20", "date_of_joining": "2026-01-01",
		"status": "Active", "bank_ac_no": "223456789012",
		"custom_malaysia_citizenship_status": "Malaysian Citizen",
		"custom_malaysia_statutory_profile": SOCSO_EIS_LINDUNG_PROFILE,
		"custom_nric": "950820140002",
		"custom_tax_identification_number": None,
		"custom_epf_member_number": None,
		"custom_socso_category": "First", "custom_eis_eligible": 1,
		"custom_lindung_participation": "Participating",
		"custom_lindung_registration_date": None,
		"custom_lindung_effective_from": None,
		"custom_lindung_evidence": None,
		"custom_lindung_multiple_employers": 0,
		"custom_pcb_resident": 0, "custom_pcb_category": None, "custom_pcb_child_units": 0,
	}
	if employee:
		doc = frappe.get_doc("Employee", employee)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Employee", **values}).insert(ignore_permissions=True)
		employee = doc.name
	return employee


def _assign_structure(employee: str) -> None:
	payable, _ = _accounts()
	structure_name = "MW Lean Monthly Salary"
	if not frappe.db.exists("Salary Structure Assignment", {
		"employee": employee, "salary_structure": structure_name, "docstatus": 1,
	}):
		assignment = frappe.get_doc({
			"doctype": "Salary Structure Assignment", "employee": employee,
			"salary_structure": structure_name, "company": COMPANY, "from_date": "2026-01-01",
			"base": 5000, "currency": "MYR", "payroll_payable_account": payable,
		}).insert(ignore_permissions=True)
		assignment.submit()


def _statutory_dict(slip) -> dict:
	return {
		row.scheme: {
			"employee": float(row.employee_amount or 0),
			"employer": float(row.employer_amount or 0),
			"extra": float(row.extra_employee_amount or 0),
			"wages": float(row.wage_base or 0),
			"applicable": int(row.applicable),
		}
		for row in slip.custom_malaysia_statutory_results
	}


def _clear_period_slips(employee: str, start, end) -> None:
	frappe.set_user("Administrator")
	for name in frappe.get_all(
		"Salary Slip",
		filters={"employee": employee, "company": COMPANY,
			"start_date": [">=", start], "end_date": ["<=", end]},
		pluck="name",
	):
		doc = frappe.get_doc("Salary Slip", name)
		if doc.docstatus == 1:
			doc.cancel()
		doc.delete()
	frappe.db.commit()


def _mixed_payroll_entry(employees: list[str], start, end):
	name = frappe.db.get_value("Payroll Entry", {
		"company": COMPANY, "start_date": start, "end_date": end, "docstatus": 0,
	}, "name")
	if name:
		return frappe.get_doc("Payroll Entry", name)
	payable, _ = _accounts()
	frappe.set_user(PAYROLL_OWNER)
	entry = frappe.get_doc({
		"doctype": "Payroll Entry", "company": COMPANY, "posting_date": end,
		"payroll_frequency": "Monthly", "start_date": start, "end_date": end,
		"currency": "MYR", "exchange_rate": 1, "payroll_payable_account": payable,
		"cost_center": frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 0}, "name"),
	}).insert()
	entry.fill_employee_details()
	wanted = set(employees)
	entry.employees = [row for row in entry.employees if row.employee in wanted]
	if {row.employee for row in entry.employees} != wanted:
		frappe.throw(f"Mixed Payroll Entry is missing employees: {wanted - {row.employee for row in entry.employees}}.")
	entry.save()
	return entry


def _june_filing(authority: str):
	frappe.set_user(PAYROLL_RELEASER)
	name = frappe.db.get_value("Malaysia Statutory Filing", {
		"company": COMPANY, "authority": authority,
		"period_start": JUNE_START, "period_end": JUNE_END, "docstatus": ["<", 2],
	}, "name")
	if name:
		doc = frappe.get_doc("Malaysia Statutory Filing", name)
	else:
		doc = frappe.get_doc({
			"doctype": "Malaysia Statutory Filing", "company": COMPANY, "authority": authority,
			"period_start": JUNE_START, "period_end": JUNE_END,
		}).insert()
	if doc.docstatus == 0:
		doc.prepare()
		doc.reload()
	return doc


def _expect_blocked(action, *, message: str):
	try:
		action()
	except frappe.ValidationError:
		frappe.clear_last_message()
		return True
	frappe.throw(message)


def run_statutory_profile(*, commit: bool = True) -> dict:
	"""Exercise the SOCSO + EIS — LINDUNG Optional profile end to end in June 2026."""
	from frappe.utils import flt, getdate

	from malaysia_workforce.malaysia_workforce.report.malaysia_annual_remuneration.malaysia_annual_remuneration import execute as annual_report
	from malaysia_workforce.malaysia_workforce.report.malaysia_payroll_readiness.malaysia_payroll_readiness import execute as readiness_report
	from malaysia_workforce.payroll.events import check_readiness, employee_readiness
	from malaysia_workforce.payroll.profile import SOCSO_EIS_LINDUNG_PROFILE, STATUTORY_PROFILE_FIELD
	from malaysia_workforce.statutory.calculators.eis import calculate_eis
	from malaysia_workforce.statutory.calculators.socso import calculate_socso
	from malaysia_workforce.statutory.filing import validate_filing_source

	seed = seed_browser_site(commit=True)
	aina = seed["employee"]
	_payroll_setup(aina)
	contractor = _contractor_employee()
	_contract(contractor)
	_assign_structure(contractor)
	frappe.set_user("Administrator")

	issues = employee_readiness(contractor, COMPANY, JUNE_END)
	if issues:
		frappe.throw(f"Contractor readiness should pass without TIN, EPF or PCB category: {issues}")

	# SOCSO Category and EIS Eligible are auto-derived from Date of Birth (age >= 60 means
	# Second Category and EIS-ineligible), so a 60+ contractor with correctly auto-derived
	# values must NOT fail readiness over that — it is the age-correct state, not a setup gap.
	original_snapshot = frappe.db.get_value(
		"Employee", contractor, ["date_of_birth", "custom_socso_category", "custom_eis_eligible"], as_dict=True
	)
	frappe.db.set_value(
		"Employee", contractor,
		{"date_of_birth": date(1960, 1, 1), "custom_socso_category": "Second", "custom_eis_eligible": 0},
		update_modified=False,
	)
	sixty_plus_issues = " ".join(employee_readiness(contractor, COMPANY, JUNE_END))
	frappe.db.set_value("Employee", contractor, dict(original_snapshot), update_modified=False)
	if "EIS" in sixty_plus_issues:
		frappe.throw(f"A 60+ contractor with correctly auto-derived EIS ineligibility should not fail readiness: {sixty_plus_issues}")

	original_socso = frappe.db.get_value("Employee", contractor, "custom_socso_category")
	frappe.db.set_value("Employee", contractor, "custom_socso_category", None, update_modified=False)
	socso_issues = " ".join(employee_readiness(contractor, COMPANY, JUNE_END))
	frappe.db.set_value("Employee", contractor, "custom_socso_category", original_socso, update_modified=False)
	if "SOCSO Category" not in socso_issues:
		frappe.throw(f"Missing SOCSO category did not fail contractor readiness: {socso_issues}")

	component_name = "MW Contractor Unclassified Earning"
	structure_name = "MW Contractor Unclassified Structure"
	created_component = not frappe.db.exists("Salary Component", component_name)
	payable, expense = _accounts()
	if created_component:
		frappe.get_doc({
			"doctype": "Salary Component", "salary_component": component_name,
			"salary_component_abbr": "MWCU", "type": "Earning",
			"accounts": [{"company": COMPANY, "account": expense}],
		}).insert(ignore_permissions=True)
	if not frappe.db.exists("Salary Structure", structure_name):
		structure = frappe.get_doc({
			"doctype": "Salary Structure", "name": structure_name, "company": COMPANY,
			"is_active": "Yes", "payroll_frequency": "Monthly", "currency": "MYR",
			"earnings": [{"salary_component": component_name, "amount": 5000}],
		}).insert(ignore_permissions=True)
		structure.submit()
	bad_assignment = frappe.get_doc({
		"doctype": "Salary Structure Assignment", "employee": contractor,
		"salary_structure": structure_name, "company": COMPANY, "from_date": "2026-06-01",
		"base": 5000, "currency": "MYR", "payroll_payable_account": payable,
	}).insert(ignore_permissions=True)
	bad_assignment.submit()
	wage_issues = " ".join(employee_readiness(contractor, COMPANY, JUNE_END))
	bad_assignment.cancel()
	bad_assignment.delete()
	if "SOCSO wages" not in wage_issues or "EIS wages" not in wage_issues:
		frappe.throw(f"Unclassified contractor earnings did not fail readiness: {wage_issues}")

	_clear_period_slips(aina, JUNE_START, JUNE_END)
	_clear_period_slips(contractor, JUNE_START, JUNE_END)
	aina_baseline = _statutory_dict(_submit_standalone_slip(aina, JUNE_START, JUNE_END))
	_clear_period_slips(aina, JUNE_START, JUNE_END)

	entry = _mixed_payroll_entry([aina, contractor], JUNE_START, JUNE_END)
	readiness = check_readiness(entry.name)
	frappe.db.commit()
	if entry.docstatus == 0:
		entry.submit()
	entry.reload()
	if frappe.db.exists("Salary Slip", {"payroll_entry": entry.name, "docstatus": 0}):
		entry.submit_salary_slips()
	entry.reload()
	slips = frappe.get_all(
		"Salary Slip",
		filters={"payroll_entry": entry.name, "docstatus": 1},
		fields=["name", "employee"],
	)
	if {row.employee for row in slips} != {aina, contractor} or len(slips) != 2:
		frappe.throw(f"Expected mixed June slips for Aina and the contractor, found {slips}.")
	by_employee = {row.employee: frappe.get_doc("Salary Slip", row.name) for row in slips}
	aina_slip = by_employee[aina]
	contractor_slip = by_employee[contractor]
	if _statutory_dict(aina_slip) != aina_baseline:
		frappe.throw("Aina's mixed-Payroll-Entry totals drifted from the solo June snapshot.")

	contractor_rows = _statutory_dict(contractor_slip)
	expected_socso = calculate_socso(
		5000, "First", contribution_date=getdate(JUNE_END), lindung_participation="Participating",
	)
	expected_eis = calculate_eis(5000)
	if abs(flt(contractor_rows["SOCSO"]["employee"]) - float(expected_socso.employee)) > 0.005:
		frappe.throw(f"Contractor SOCSO employee amount mismatch: {contractor_rows['SOCSO']}.")
	if abs(flt(contractor_rows["SOCSO"]["extra"]) - float(expected_socso.extra_employee)) > 0.005:
		frappe.throw(f"Contractor SKBBK amount mismatch: {contractor_rows['SOCSO']}.")
	if abs(flt(contractor_rows["EIS"]["employee"]) - float(expected_eis.employee)) > 0.005:
		frappe.throw(f"Contractor EIS amount mismatch: {contractor_rows['EIS']}.")
	if not contractor_rows["SOCSO"]["applicable"] or not contractor_rows["EIS"]["applicable"]:
		frappe.throw(f"Contractor SOCSO/EIS must be applicable: {contractor_rows}.")
	for scheme in ("EPF", "HRD Corp", "PCB", "CP38", "Zakat"):
		row = contractor_rows[scheme]
		if row["applicable"] or any(row[key] for key in ("employee", "employer", "extra")):
			frappe.throw(f"Contractor {scheme} must be inapplicable with zero amounts: {row}.")
	deduction_names = {row.salary_component for row in contractor_slip.deductions}
	for component in ("PCB", "CP38", "Zakat", "EPF Employee"):
		if component in deduction_names:
			frappe.throw(f"Contractor slip still has {component} deduction.")

	perkeso = _june_filing("PERKESO")
	epf = _june_filing("EPF")
	lhdn = _june_filing("LHDN")
	perkeso_employees = {row.employee for row in perkeso.employee_lines}
	if contractor not in perkeso_employees or aina not in perkeso_employees:
		frappe.throw(f"June PERKESO must include both employees: {perkeso_employees}.")
	contractor_line = next(row for row in perkeso.employee_lines if row.employee == contractor)
	if not flt(contractor_line.employee_amount) or not flt(contractor_line.additional_amount):
		frappe.throw(f"June PERKESO contractor line is missing SOCSO/EIS/SKBBK: {contractor_line.as_dict()}.")
	if contractor in {row.employee for row in epf.employee_lines}:
		frappe.throw("June EPF filing included the contractor.")
	if contractor in {row.employee for row in lhdn.employee_lines}:
		frappe.throw("June LHDN filing included the contractor.")

	frappe.set_user(HR_MANAGER)
	_expect_blocked(
		lambda: frappe.get_doc({
			"doctype": "Malaysia Tax Declaration TP1", "employee": contractor, "company": COMPANY,
			"tax_year": 2026, "declaration_date": "2026-06-01", "employee_declaration": 1,
		}).insert(),
		message="TP1 was allowed for the contractor profile.",
	)
	_expect_blocked(
		lambda: frappe.get_doc({
			"doctype": "Malaysia Previous Employment TP3", "employee": contractor, "company": COMPANY,
			"tax_year": 2026, "previous_employer_name": "Prior Contractor Sdn Bhd",
			"employee_declaration": 1,
		}).insert(),
		message="TP3 was allowed for the contractor profile.",
	)
	_expect_blocked(
		lambda: frappe.get_doc({
			"doctype": "Malaysia CP38 Directive", "employee": contractor, "company": COMPANY,
			"directive_reference": "CP38-CONTRACTOR-BLOCK", "effective_from": "2026-06-01",
			"directive_amount": 100, "monthly_deduction": 50,
			"evidence": _private_file("mw-contractor-cp38.txt", "Should not be accepted"),
		}).insert(),
		message="A CP38 directive was allowed for the contractor profile.",
	)

	frappe.set_user(HR_MANAGER)
	visible = frappe.get_doc("Salary Slip", contractor_slip.name)
	if visible.get(STATUTORY_PROFILE_FIELD) != SOCSO_EIS_LINDUNG_PROFILE:
		frappe.throw("HR Manager cannot read the Salary Slip Statutory Profile snapshot.")

	for user in (HR_MANAGER, PAYROLL_RELEASER):
		frappe.set_user(user)
		_, default_rows = annual_report({"company": COMPANY, "year": 2026})
		_, all_rows = annual_report({"company": COMPANY, "year": 2026, "show_all_profiles": 1})
		default_employees = {row["employee"] for row in default_rows}
		all_employees = {row["employee"] for row in all_rows}
		if contractor in default_employees:
			frappe.throw(f"{user} saw the contractor on the default annual report.")
		if contractor not in all_employees:
			frappe.throw(f"{user} did not see the contractor when Show All Statutory Profiles was ticked.")

	# Administrator can list Employee but has no permlevel-1 grant; get_all must
	# still return the real snapshot. System Manager is on the report's role
	# list but ERPNext's Employee DocType has no System Manager permission row.
	frappe.set_user("Administrator")
	_, ready_rows = readiness_report({"company": COMPANY, "payroll_date": JUNE_END, "show_ready": 1})
	contractor_ready = next((row for row in ready_rows if row.get("employee") == contractor), None)
	if not contractor_ready or contractor_ready.get("profile") != SOCSO_EIS_LINDUNG_PROFILE:
		frappe.throw(f"Readiness hid the contractor profile: {contractor_ready}.")

	frappe.set_user("Administrator")
	original_profile = frappe.db.get_value("Employee", contractor, STATUTORY_PROFILE_FIELD)
	submitted_snapshot = contractor_slip.get(STATUTORY_PROFILE_FIELD)
	draft = _mixed_payroll_entry([contractor], date(2026, 5, 1), date(2026, 5, 31))
	draft_slip = None
	if draft.docstatus == 0:
		draft_slip = frappe.get_doc({
			"doctype": "Salary Slip", "employee": contractor, "company": COMPANY,
			"payroll_frequency": "Monthly", "start_date": "2026-05-01", "end_date": "2026-05-31",
			"posting_date": "2026-05-31", "payroll_entry": draft.name,
		}).insert(ignore_permissions=True)
	frappe.db.set_value(
		"Employee", contractor, STATUTORY_PROFILE_FIELD, "Standard Payroll", update_modified=False,
	)
	contractor_slip.reload()
	if contractor_slip.get(STATUTORY_PROFILE_FIELD) != submitted_snapshot:
		frappe.throw("Changing the Employee profile recalculated a submitted Salary Slip.")
	_expect_blocked(
		lambda: validate_filing_source(perkeso),
		message="validate_filing_source did not notice the Employee profile change.",
	)
	if draft.docstatus == 0:
		_expect_blocked(
			draft.submit,
			message="Payroll Entry submit accepted a stale Statutory Profile snapshot.",
		)
	if draft_slip:
		_expect_blocked(
			draft_slip.submit,
			message="Direct Salary Slip submit accepted a stale Statutory Profile snapshot.",
		)
		draft_slip.reload()
		if draft_slip.docstatus != 0:
			frappe.throw("The stale draft Salary Slip was submitted.")
		draft_slip.delete(ignore_permissions=True)
	if draft.docstatus == 0:
		draft.delete(ignore_permissions=True)
	frappe.db.set_value(
		"Employee", contractor, STATUTORY_PROFILE_FIELD, original_profile, update_modified=False,
	)

	frappe.set_user("Administrator")
	result = {
		"seed": seed,
		"contractor": contractor,
		"payroll_entry": entry.name,
		"readiness": readiness["status"],
		"aina_slip": aina_slip.name,
		"contractor_slip": contractor_slip.name,
		"contractor_statutory": contractor_rows,
		"filings": {
			"perkeso": perkeso.name,
			"epf_excludes_contractor": contractor not in {row.employee for row in epf.employee_lines},
			"lhdn_excludes_contractor": contractor not in {row.employee for row in lhdn.employee_lines},
		},
	}
	if commit:
		frappe.db.commit()
	return result


# ---------------------------------------------------------------------------
# Regression scenarios for the payroll fixes (structure overrides, zakat routes,
# multi-slip wage bases, C11 sublimits, submission consistency, account readiness).
# ---------------------------------------------------------------------------

from decimal import Decimal as _D  # noqa: E402


def _fix_reset() -> None:
	"""Remove prior scenario artefacts so the scenario can be re-run.

	Only drafts that include this scenario's employees are touched, so filings created
	by other live scenarios (which may already be accepted or reconciled) are left alone.
	"""
	fix_employees = {
		name
		for name in frappe.get_all("Employee", filters={"employee_number": ["like", "MWF%"]}, pluck="name")
	}
	for name in frappe.get_all("Malaysia Statutory Filing", filters={"company": COMPANY, "docstatus": 0}, pluck="name"):
		doc = frappe.get_doc("Malaysia Statutory Filing", name)
		if fix_employees.intersection({row.employee for row in doc.employee_lines}):
			frappe.delete_doc("Malaysia Statutory Filing", name, force=True, ignore_permissions=True)
	for employee in fix_employees:
		for doctype in ("Salary Slip", "Additional Salary", "Salary Structure Assignment",
			"Malaysia Tax Declaration TP1", "Malaysia Previous Employment TP3"):
			for name in frappe.get_all(doctype, filters={"employee": employee}, pluck="name"):
				doc = frappe.get_doc(doctype, name)
				if doc.docstatus == 1:
					doc.cancel()
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	for name in frappe.get_all("Salary Structure", filters={"name": ["like", "MW Fix%"]}, pluck="name"):
		doc = frappe.get_doc("Salary Structure", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Salary Structure", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _fix_employee(key: str, base: int, *, child_units: int = 0) -> str:
	number = f"MWF{key}"
	name = frappe.db.get_value("Employee", {"employee_number": number}, "name")
	values = {
		"first_name": f"Fix {key}", "last_name": "Tester", "employee_number": number,
		"company": COMPANY, "designation": "Barista", "gender": "Female",
		"date_of_birth": "1992-03-10", "date_of_joining": "2026-01-01", "status": "Active",
		"custom_malaysia_citizenship_status": "Malaysian Citizen",
		"custom_nric": f"92031014{ord(key):04d}", "custom_tax_identification_number": f"IG{ord(key):08d}",
		"custom_epf_member_number": f"90{ord(key):06d}",
		"custom_socso_category": "First", "custom_eis_eligible": 1,
		"custom_lindung_participation": "Participating",
		"custom_lindung_registration_date": None, "custom_lindung_effective_from": None,
		"custom_lindung_evidence": None, "custom_lindung_multiple_employers": 0,
		"custom_pcb_resident": 1, "custom_pcb_category": "1 - Single", "custom_pcb_child_units": child_units,
	}
	if name:
		doc = frappe.get_doc("Employee", name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Employee", **values}).insert(ignore_permissions=True)
		name = doc.name
	if not frappe.db.exists("Contract", {"party_type": "Employee", "party_name": name, "docstatus": 1}):
		contract = frappe.get_doc({
			"doctype": "Contract", "party_type": "Employee", "party_name": name, "is_signed": 1,
			"start_date": "2026-01-01", "contract_terms": "Synthetic contract for regression testing.",
			"custom_malaysia_wage_basis": "Monthly", "custom_malaysia_work_classification": "Full-time",
			"custom_contract_wage_rate": base, "custom_normal_hours_per_day": 8,
			"custom_normal_hours_per_week": 45, "custom_rest_day": "Sunday", "custom_overtime_eligible": 1,
		}).insert(ignore_permissions=True)
		contract.submit()
	return name


def _fix_structure(name: str, base: int, *, managed_deduction: tuple[str, int] | None = None) -> str:
	deductions = []
	if managed_deduction:
		component, amount = managed_deduction
		deductions.append({"salary_component": component, "amount": amount})
	doc = frappe.get_doc({
		"doctype": "Salary Structure", "name": name, "company": COMPANY, "is_active": "Yes",
		"payroll_frequency": "Monthly", "currency": "MYR",
		"earnings": [{"salary_component": "MW Lean Basic Pay", "amount": base}],
		"deductions": deductions,
	}).insert(ignore_permissions=True)
	doc.submit()
	return name


def _fix_assign(employee: str, structure: str, base: int) -> None:
	payable, _expense = _accounts()
	assignment = frappe.get_doc({
		"doctype": "Salary Structure Assignment", "employee": employee, "salary_structure": structure,
		"company": COMPANY, "from_date": "2026-01-01", "base": base, "currency": "MYR",
		"payroll_payable_account": payable,
	}).insert(ignore_permissions=True)
	assignment.submit()


def _fix_slip(employee: str, structure: str, start, end, *, submit: bool = True):
	doc = frappe.get_doc({
		"doctype": "Salary Slip", "employee": employee, "company": COMPANY,
		"salary_structure": structure, "payroll_frequency": "Monthly",
		"start_date": start, "end_date": end, "posting_date": end, "currency": "MYR",
	}).insert(ignore_permissions=True)
	if submit:
		doc.submit()
		doc.reload()
	return doc


def _fix_deduction(slip, component: str) -> _D:
	return sum(
		(_D(str(row.amount or 0)) for row in slip.deductions if row.salary_component == component),
		_D("0"),
	)


def _fix_result(slip, scheme: str):
	rows = [row for row in slip.custom_malaysia_statutory_results if row.scheme == scheme]
	return rows[0] if rows else None


def _fix_check(results: list, label: str, actual, expected) -> None:
	if isinstance(actual, bool) or isinstance(expected, bool):
		results.append({"check": label, "expected": str(bool(expected)),
			"actual": str(bool(actual)), "ok": bool(actual) == bool(expected)})
		return
	actual_d = _D(str(actual if actual is not None else 0))
	expected_d = _D(str(expected))
	results.append({"check": label, "expected": str(expected_d), "actual": str(actual_d), "ok": actual_d == expected_d})


def _fix_filing(authority: str, start, end):
	filing = frappe.get_doc({
		"doctype": "Malaysia Statutory Filing", "company": COMPANY, "authority": authority,
		"period_start": start, "period_end": end,
	}).insert(ignore_permissions=True)
	from malaysia_workforce.statutory.filing import prepare_filing

	prepare_filing(filing)
	filing.reload()
	return filing


def _fix_line(filing, employee: str):
	for row in filing.employee_lines:
		if row.employee == employee:
			return row
	raise AssertionError(f"{employee} is missing from {filing.name}")


def run_payroll_fixes(*, commit: bool = True) -> dict:
	"""Behaviour checks through Salary Slip validation/submission and filing preparation.

	Expected amounts come from the official EPF Third Schedule (effective 1 October 2025),
	the PERKESO contribution table including SKBBK, the EIS schedule and the LHDN 2026
	computerised MTD specification, not from the app's own calculators.
	"""
	frappe.set_user("Administrator")
	results: list[dict] = []
	_company()
	_holiday_setup()
	_fiscal_year_setup()
	_payroll_period_setup()
	_user(HR_MANAGER, "Maya", ("HR Manager", "HR User"))
	if not frappe.db.exists("Gender", "Female"):
		frappe.get_doc({"doctype": "Gender", "gender": "Female"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Designation", "Barista"):
		frappe.get_doc({"doctype": "Designation", "designation_name": "Barista"}).insert(ignore_permissions=True)
	frappe.db.set_single_value("Payroll Settings", "include_holidays_in_total_working_days", 1)
	_payable, expense = _accounts()
	_salary_component("MW Lean Basic Pay", "MWLB", treatment="Regular Remuneration", expense=expense)
	_salary_component("MW Lean Bonus", "MWBN", treatment="Additional Remuneration", expense=expense)
	_fix_reset()

	# 1. A Salary Structure that also carries a managed statutory deduction must not
	#    override the calculated amount (previously EPF was replaced by the structure value).
	emp_a = _fix_employee("A", 5000)
	_fix_assign(emp_a, _fix_structure("MW Fix A", 5000, managed_deduction=("EPF Employee", 1)), 5000)
	slip_a = _fix_slip(emp_a, "MW Fix A", date(2026, 1, 1), date(2026, 1, 31))
	_fix_check(results, "A EPF deduction (structure said RM1)", _fix_deduction(slip_a, "EPF Employee"), "550.00")
	_fix_check(results, "A EPF result", _fix_result(slip_a, "EPF").employee_amount, "550.00")
	_fix_check(results, "A EPF employer result", _fix_result(slip_a, "EPF").employer_amount, "650.00")
	_fix_check(results, "A SOCSO deduction", _fix_deduction(slip_a, "SOCSO Employee"), "24.75")
	# LINDUNG 24 Jam starts with the June 2026 contribution month, so January has none.
	_fix_check(results, "A SKBBK deduction before June 2026", _fix_deduction(slip_a, "SKBBK Employee"), "0.00")
	_fix_check(results, "A EIS deduction", _fix_deduction(slip_a, "EIS Employee"), "9.90")
	_fix_check(results, "A PCB deduction", _fix_deduction(slip_a, "PCB"), "110.00")
	_fix_check(results, "A net pay = gross - deductions", slip_a.net_pay,
		_D(str(slip_a.gross_pay)) - _D(str(slip_a.total_deduction)))

	# 2. Zakat supplied as an Additional Salary is deducted exactly once.
	emp_b = _fix_employee("B", 5000)
	_fix_assign(emp_b, _fix_structure("MW Fix B", 5000), 5000)
	zakat = frappe.get_doc({
		"doctype": "Additional Salary", "employee": emp_b, "company": COMPANY,
		"salary_component": "Zakat", "amount": 100, "payroll_date": date(2026, 1, 31),
	}).insert(ignore_permissions=True)
	zakat.submit()
	slip_b = _fix_slip(emp_b, "MW Fix B", date(2026, 1, 1), date(2026, 1, 31))
	_fix_check(results, "B zakat rows", len([r for r in slip_b.deductions if r.salary_component == "Zakat"]), "1")
	_fix_check(results, "B zakat deducted", _fix_deduction(slip_b, "Zakat"), "100.00")
	_fix_check(results, "B zakat statutory result", _fix_result(slip_b, "Zakat").employee_amount, "100.00")
	# MTD RM110 less the RM100 zakat deducted this month.
	_fix_check(results, "B PCB after zakat", _fix_deduction(slip_b, "PCB"), "10.00")

	# 2b. The same zakat deduction supplied through the Salary Structure is also
	#     deducted once (the route the stock setup uses).
	emp_g = _fix_employee("G", 5000)
	_fix_assign(emp_g, _fix_structure("MW Fix G", 5000, managed_deduction=("Zakat", 100)), 5000)
	slip_g = _fix_slip(emp_g, "MW Fix G", date(2026, 1, 1), date(2026, 1, 31))
	_fix_check(results, "G structure zakat rows",
		len([r for r in slip_g.deductions if r.salary_component == "Zakat"]), "1")
	_fix_check(results, "G structure zakat deducted", _fix_deduction(slip_g, "Zakat"), "100.00")
	_fix_check(results, "G PCB after structure zakat", _fix_deduction(slip_g, "PCB"), "10.00")

	# 3. Two slips of RM2,000 in one month: the authority wage is RM4,000, not the
	#    sum of the cumulative bases (RM2,000 + RM4,000 = RM6,000).
	emp_c = _fix_employee("C", 2000)
	_fix_assign(emp_c, _fix_structure("MW Fix C", 2000), 2000)
	_fix_slip(emp_c, "MW Fix C", date(2026, 9, 1), date(2026, 9, 15))
	slip_c2 = _fix_slip(emp_c, "MW Fix C", date(2026, 9, 16), date(2026, 9, 30))
	_fix_check(results, "C month EPF employee (2 x RM2,000)",
		_D(str(_fix_result(slip_c2, "EPF").employee_amount)) + _D("220.00"), "440.00")
	_fix_check(results, "C month SOCSO employee",
		_D(str(_fix_result(slip_c2, "SOCSO").employee_amount)) + _D("9.75"), "19.75")
	_fix_check(results, "C month HRD levy",
		_D(str(_fix_result(slip_c2, "HRD Corp").employer_amount)) + _D("20.00"), "40.00")

	# 4. Three slips of RM2,000 in October: RM6,000 of wages, HRD levy RM60
	#    (repeated accumulation used to make this RM80 and report RM14,000 of wages).
	_fix_slip(emp_c, "MW Fix C", date(2026, 10, 1), date(2026, 10, 10))
	_fix_slip(emp_c, "MW Fix C", date(2026, 10, 11), date(2026, 10, 20))
	slip_c3 = _fix_slip(emp_c, "MW Fix C", date(2026, 10, 21), date(2026, 10, 31))
	_fix_check(results, "C three-slip SOCSO employee (ceiling)",
		_D(str(_fix_result(slip_c3, "SOCSO").employee_amount)) + _D("9.75") + _D("10.00"), "29.75")
	_fix_check(results, "C three-slip HRD levy",
		_D(str(_fix_result(slip_c3, "HRD Corp").employer_amount)) + _D("20.00") + _D("20.00"), "60.00")

	# 5. A bonus slip in the same month keeps regular/additional wages apart, takes
	#    the month base to RM11,000 and the SOCSO base to its RM6,000 ceiling.
	emp_d = _fix_employee("D", 5000)
	_fix_assign(emp_d, _fix_structure("MW Fix D", 5000), 5000)
	_fix_slip(emp_d, "MW Fix D", date(2026, 9, 1), date(2026, 9, 15))
	bonus = frappe.get_doc({
		"doctype": "Additional Salary", "employee": emp_d, "company": COMPANY,
		"salary_component": "MW Lean Bonus", "amount": 1000, "payroll_date": date(2026, 9, 20),
	}).insert(ignore_permissions=True)
	bonus.submit()
	slip_d2 = _fix_slip(emp_d, "MW Fix D", date(2026, 9, 16), date(2026, 9, 30))
	_fix_check(results, "D bonus slip EPF employee delta", _fix_result(slip_d2, "EPF").employee_amount, "660.00")
	_fix_check(results, "D month EPF employee",
		_D(str(_fix_result(slip_d2, "EPF").employee_amount)) + _D("550.00"), "1210.00")
	_fix_check(results, "D bonus additional wages", _fix_result(slip_d2, "PCB").additional_wages, "1000.00")
	_fix_check(results, "D SOCSO capped at ceiling",
		_D(str(_fix_result(slip_d2, "SOCSO").employee_amount)) + _D("24.75"), "29.75")

	# 6. Filings use each slip's own wage base.
	perkeso_sep = _fix_filing("PERKESO", date(2026, 9, 1), date(2026, 9, 30))
	_fix_check(results, "PERKESO Sep C wages", _fix_line(perkeso_sep, emp_c).wages, "4000.00")
	_fix_check(results, "PERKESO Sep C employee total", _fix_line(perkeso_sep, emp_c).employee_amount, "27.65")
	_fix_check(results, "PERKESO Sep C SKBBK", _fix_line(perkeso_sep, emp_c).additional_amount, "29.65")
	_fix_check(results, "PERKESO Sep D wages", _fix_line(perkeso_sep, emp_d).wages, "11000.00")
	_fix_check(results, "PERKESO Sep D employee total", _fix_line(perkeso_sep, emp_d).employee_amount, "41.65")
	epf_sep = _fix_filing("EPF", date(2026, 9, 1), date(2026, 9, 30))
	_fix_check(results, "EPF Sep C wages", _fix_line(epf_sep, emp_c).wages, "4000.00")
	_fix_check(results, "EPF Sep C employee total", _fix_line(epf_sep, emp_c).employee_amount, "440.00")
	_fix_check(results, "EPF Sep C employer total", _fix_line(epf_sep, emp_c).employer_amount, "520.00")
	perkeso_oct = _fix_filing("PERKESO", date(2026, 10, 1), date(2026, 10, 31))
	_fix_check(results, "PERKESO Oct three-slip wages", _fix_line(perkeso_oct, emp_c).wages, "6000.00")
	_fix_check(results, "PERKESO Oct three-slip employee total", _fix_line(perkeso_oct, emp_c).employee_amount, "41.65")
	hrd_oct = _fix_filing("HRD Corp", date(2026, 10, 1), date(2026, 10, 31))
	_fix_check(results, "HRD Oct three-slip wages", _fix_line(hrd_oct, emp_c).wages, "6000.00")
	_fix_check(results, "HRD Oct three-slip levy", _fix_line(hrd_oct, emp_c).employer_amount, "60.00")

	# 7. TP1 claim month: C11B is ignored before its month, applied in it, and carried
	#    afterwards. LHDN 2026 spec: sum-LP accumulates claims, LP1 is the claim month.
	emp_e = _fix_employee("E", 5000)
	_fix_assign(emp_e, _fix_structure("MW Fix E", 5000), 5000)
	receipt = _private_file("mw-fix-c11-receipt.txt", "Synthetic C11B evidence")
	tp1 = frappe.get_doc({
		"doctype": "Malaysia Tax Declaration TP1", "employee": emp_e, "company": COMPANY,
		"tax_year": 2026, "declaration_date": "2026-02-01", "employee_declaration": 1,
		"relief_claims": [{"relief_code": "C11B", "amount": 3000, "claim_month": 2,
			"evidence_reference": receipt}],
	}).insert(ignore_permissions=True)
	frappe.set_user(HR_MANAGER)
	tp1.submit()
	frappe.set_user("Administrator")
	slip_e_jan = _fix_slip(emp_e, "MW Fix E", date(2026, 1, 1), date(2026, 1, 31))
	slip_e_feb = _fix_slip(emp_e, "MW Fix E", date(2026, 2, 1), date(2026, 2, 28))
	slip_e_mar = _fix_slip(emp_e, "MW Fix E", date(2026, 3, 1), date(2026, 3, 31))
	_fix_check(results, "E PCB before claim month", _fix_deduction(slip_e_jan, "PCB"), "110.00")
	_fix_check(results, "E PCB in claim month", _fix_deduction(slip_e_feb, "PCB"), "93.65")
	_fix_check(results, "E PCB after claim month", _fix_deduction(slip_e_mar, "PCB"), "93.65")

	# 7b. C11 combined with a bonus and a previous employer's EPF. The RM4,000 EPF
	#     sublimit is already filled by RM1,100 (TP3) + RM550 (January) + RM220 (bonus
	#     EPF) + RM2,130 projected, so C11A adds nothing and only C11B applies.
	emp_h = _fix_employee("H", 5000)
	_fix_assign(emp_h, _fix_structure("MW Fix H", 5000), 5000)
	tp3_evidence = _private_file("mw-fix-tp3-evidence.txt", "Synthetic TP3 evidence")
	tp3 = frappe.get_doc({
		"doctype": "Malaysia Previous Employment TP3", "employee": emp_h, "company": COMPANY,
		"tax_year": 2026, "previous_employer_name": "Previous Employer Sdn Bhd",
		"employment_start": "2026-01-01", "employment_end": "2026-01-20",
		"gross_normal_remuneration": 10000, "epf_contribution": 1100, "mtd_paid": 0,
		"zakat_paid": 0, "optional_reliefs": 0, "evidence": tp3_evidence,
		"employee_declaration": 1,
	}).insert(ignore_permissions=True)
	tp1_h = frappe.get_doc({
		"doctype": "Malaysia Tax Declaration TP1", "employee": emp_h, "company": COMPANY,
		"tax_year": 2026, "declaration_date": "2026-02-01", "employee_declaration": 1,
		"relief_claims": [
			{"relief_code": "C11A", "amount": 4000, "claim_month": 2, "evidence_reference": receipt},
			{"relief_code": "C11B", "amount": 3000, "claim_month": 2, "evidence_reference": receipt},
		],
	}).insert(ignore_permissions=True)
	frappe.set_user(HR_MANAGER)
	tp3.submit()
	tp1_h.submit()
	frappe.set_user("Administrator")
	slip_h_jan = _fix_slip(emp_h, "MW Fix H", date(2026, 1, 1), date(2026, 1, 31))
	bonus_h = frappe.get_doc({
		"doctype": "Additional Salary", "employee": emp_h, "company": COMPANY,
		"salary_component": "MW Lean Bonus", "amount": 2000, "payroll_date": date(2026, 2, 15),
	}).insert(ignore_permissions=True)
	bonus_h.submit()
	slip_h_feb = _fix_slip(emp_h, "MW Fix H", date(2026, 2, 1), date(2026, 2, 28))
	# January: P = (10,000 - 1,100) + (5,000 - 550) + (5,000 - 213.63) x 11 - 9,000
	# = 57,000.07; tax 2,270.00; MTD 2,270/12 = 189.17 rounded up to five sen = 189.20.
	_fix_check(results, "H PCB before C11 and with TP3", _fix_deduction(slip_h_jan, "PCB"), "189.20")
	# February adds the RM2,000 bonus in the same slip: P2 56,000, EPF relief 4,000, so
	# C11A adds nothing and C11B adds 3,000. P1 54,000; normal MTD 159.20; additional
	# 2,160.00 - (189.20 + 159.20 x 11) = 219.60; total 378.80.
	_fix_check(results, "H PCB with C11A capped and C11B applied", _fix_deduction(slip_h_feb, "PCB"), "378.80")
	_fix_check(results, "H bonus additional wages", _fix_result(slip_h_feb, "PCB").additional_wages, "2000.00")
	# One February slip with the bonus inside it, so the month's EPF is 11% of 7,000.
	_fix_check(results, "H bonus month EPF employee", _fix_result(slip_h_feb, "EPF").employee_amount, "770.00")

	# 8. Draft-to-submit: a tax-setting change after the draft must be reflected.
	emp_f = _fix_employee("F", 5000)
	_fix_assign(emp_f, _fix_structure("MW Fix F", 5000), 5000)
	draft = _fix_slip(emp_f, "MW Fix F", date(2026, 1, 1), date(2026, 1, 31), submit=False)
	_fix_check(results, "F draft PCB (no child units)", _fix_deduction(draft, "PCB"), "110.00")
	frappe.db.set_value("Employee", emp_f, "custom_pcb_child_units", 1)
	draft.reload()
	draft.submit()
	draft.reload()
	_fix_check(results, "F submitted PCB after child-unit change", _fix_deduction(draft, "PCB"), "100.00")
	_fix_check(results, "F submitted PCB result", _fix_result(draft, "PCB").employee_amount, "100.00")

	# 8b. Ambiguous legacy history blocks a new slip before the wage base is compounded.
	#     The two older slips are rewritten to look like rows from the previous build:
	#     cumulative wage bases without the per-slip marker.
	emp_i = _fix_employee("I", 2000)
	_fix_assign(emp_i, _fix_structure("MW Fix I", 2000), 2000)
	legacy_1 = _fix_slip(emp_i, "MW Fix I", date(2026, 11, 1), date(2026, 11, 10))
	legacy_2 = _fix_slip(emp_i, "MW Fix I", date(2026, 11, 11), date(2026, 11, 20))
	for row_name in frappe.get_all(
		"Malaysia Statutory Result",
		filters={"parent": ["in", [legacy_1.name, legacy_2.name]], "parenttype": "Salary Slip",
			"scheme": ["in", ["SOCSO", "EIS", "HRD Corp"]]},
		pluck="name",
	):
		frappe.db.set_value("Malaysia Statutory Result", row_name, "per_slip_wages_recorded", 0)
	legacy_blocked = False
	try:
		_fix_slip(emp_i, "MW Fix I", date(2026, 11, 21), date(2026, 11, 30))
	except frappe.ValidationError as exc:
		legacy_blocked = "earlier build" in str(exc)
	_fix_check(results, "Legacy same-month rows block a new slip", legacy_blocked, True)

	# 8c. Low normal PCB with a bonus and payroll zakat, end to end: save -> reload ->
	#     submit -> reload -> LHDN filing. RM3,700 normal plus a RM1,000 bonus gives
	#     RM29.60 additional MTD; RM5 zakat offsets it to RM24.60 (HASiL E.5(ii) rule).
	emp_j = _fix_employee("J", 3700)
	_fix_assign(emp_j, _fix_structure("MW Fix J", 3700), 3700)
	zakat_j = frappe.get_doc({
		"doctype": "Additional Salary", "employee": emp_j, "company": COMPANY,
		"salary_component": "Zakat", "amount": 5, "payroll_date": date(2026, 1, 10),
	}).insert(ignore_permissions=True)
	zakat_j.submit()
	bonus_j = frappe.get_doc({
		"doctype": "Additional Salary", "employee": emp_j, "company": COMPANY,
		"salary_component": "MW Lean Bonus", "amount": 1000, "payroll_date": date(2026, 1, 20),
	}).insert(ignore_permissions=True)
	bonus_j.submit()
	draft_j = _fix_slip(emp_j, "MW Fix J", date(2026, 1, 1), date(2026, 1, 31), submit=False)
	draft_j.reload()
	_fix_check(results, "J draft PCB before submit", _fix_deduction(draft_j, "PCB"), "24.60")
	draft_j.submit()
	draft_j.reload()
	zakat_rows_j = [row for row in draft_j.deductions if row.salary_component == "Zakat"]
	_fix_check(results, "J zakat cash deduction rows", len(zakat_rows_j), "1")
	_fix_check(results, "J zakat cash deduction", _fix_deduction(draft_j, "Zakat"), "5.00")
	_fix_check(results, "J PCB after submit", _fix_result(draft_j, "PCB").employee_amount, "24.60")
	_fix_check(results, "J PCB deduction equals result",
		_fix_deduction(draft_j, "PCB"), _fix_result(draft_j, "PCB").employee_amount)
	_fix_check(results, "J net pay = gross - deductions", draft_j.net_pay,
		_D(str(draft_j.gross_pay)) - _D(str(draft_j.total_deduction)))
	_fix_check(results, "J zakat offset recorded in saved result",
		any("Zakat not absorbed" in (row.explanation or "") for row in draft_j.custom_malaysia_statutory_results),
		"True")

	# 8d. The same month through a second slip: zakat on the first half-month slip, the
	#     bonus on the second, still exactly one cash zakat and one month PCB.
	emp_k = _fix_employee("K", 3700)
	_fix_assign(emp_k, _fix_structure("MW Fix K", 3700), 3700)
	zakat_k = frappe.get_doc({
		"doctype": "Additional Salary", "employee": emp_k, "company": COMPANY,
		"salary_component": "Zakat", "amount": 5, "payroll_date": date(2026, 1, 10),
	}).insert(ignore_permissions=True)
	zakat_k.submit()
	slip_ka = _fix_slip(emp_k, "MW Fix K", date(2026, 1, 1), date(2026, 1, 15))
	bonus_k = frappe.get_doc({
		"doctype": "Additional Salary", "employee": emp_k, "company": COMPANY,
		"salary_component": "MW Lean Bonus", "amount": 1000, "payroll_date": date(2026, 1, 20),
	}).insert(ignore_permissions=True)
	bonus_k.submit()
	slip_kb = _fix_slip(emp_k, "MW Fix K", date(2026, 1, 16), date(2026, 1, 31))
	_fix_check(results, "K first slip PCB", _fix_deduction(slip_ka, "PCB"), "0.00")
	# Month normal 7,400 + bonus 1,000. P1 uses kt=0: K2 = (4,000 - 814)/11 = 289.63,
	# P1 = 6,586 + (7,400 - 289.63) x 11 - 9,000 = 75,800.07, X1 = 4,802.01, Step[C]
	# 400.20. P2 uses kt=110: K2 = 279.63, P2 = 76,800.07, X2 = 4,992.01, additional
	# 4,992.01 - 400.20 x 12 = 189.61 -> 189.65. Zakat 5 is absorbed by the normal MTD,
	# so payable = 395.20 + 189.65 = 584.85.
	_fix_check(results, "K second slip PCB (month total)", _fix_result(slip_kb, "PCB").employee_amount, "584.85")
	_fix_check(results, "K second slip PCB deduction",
		_fix_deduction(slip_kb, "PCB"), _fix_result(slip_kb, "PCB").employee_amount)
	_fix_check(results, "K month zakat cash total",
		_fix_deduction(slip_ka, "Zakat") + _fix_deduction(slip_kb, "Zakat"), "5.00")
	_fix_check(results, "K month PCB total",
		_fix_result(slip_ka, "PCB").employee_amount + _fix_result(slip_kb, "PCB").employee_amount, "584.85")

	# 8e. LHDN filing over January: J and K lines, and CP39 counts derived from the
	#     D-lines that actually carry MTD or CP38 (Exhibit 4 fields 7 and 9).
	lhdn_jan = _fix_filing("LHDN", date(2026, 1, 1), date(2026, 1, 31))
	_fix_check(results, "LHDN Jan J MTD", _fix_line(lhdn_jan, emp_j).employee_amount, "24.60")
	_fix_check(results, "LHDN Jan K MTD", _fix_line(lhdn_jan, emp_k).employee_amount, "584.85")
	file_name = frappe.db.get_value("File", {"file_url": lhdn_jan.generated_file}, "name")
	raw_content = frappe.get_doc("File", file_name).get_content()
	file_text = raw_content.decode("ascii") if isinstance(raw_content, (bytes, bytearray)) else raw_content
	lines = file_text.splitlines()
	header, details = lines[0], lines[1:]
	mtd_lines = sum(1 for line in details if int(line[110:118]) > 0)
	cp38_lines = sum(1 for line in details if int(line[118:126]) > 0)
	_fix_check(results, "CP39 MTD record count", header[37:42], str(mtd_lines).zfill(5))
	_fix_check(results, "CP39 CP38 record count", header[52:57], str(cp38_lines).zfill(5))
	_fix_check(results, "CP39 CP38 count is zero", header[52:57], "00000")
	_fix_check(results, "CP39 detail lines kept", len(details), str(len(lhdn_jan.employee_lines)))
	_fix_check(results, "CP39 header total MTD matches lines",
		int(header[27:37]), sum(int(line[110:118]) for line in details))
	_fix_check(results, "CP39 file uses CRLF", file_text.endswith("\r\n"), "True")

	# 9. Missing Salary Component accounts are reported before payroll, naming both the
	#    component and the company (previously only the accrual journal failed).
	from malaysia_workforce.payroll.validation import missing_component_account_issues

	frappe.db.delete("Salary Component Account", {"parent": "EPF Employee", "company": COMPANY})
	issues = missing_component_account_issues(COMPANY)
	_fix_check(results, "Missing EPF account is reported",
		any("EPF Employee" in issue and COMPANY in issue for issue in issues), "True")
	payable, _expense = _accounts()
	component = frappe.get_doc("Salary Component", "EPF Employee")
	component.append("accounts", {"company": COMPANY, "account": payable})
	component.save(ignore_permissions=True)
	_fix_check(results, "Restored EPF account is accepted",
		not any("EPF Employee" in issue for issue in missing_component_account_issues(COMPANY)), "True")

	failed = [row for row in results if not row["ok"]]
	summary = {"checks": len(results), "failed": len(failed), "results": results}
	if failed:
		raise AssertionError(f"payroll fix checks failed: {failed}")
	if commit:
		frappe.db.commit()
	frappe.set_user("Administrator")
	return summary

from __future__ import annotations

from datetime import date
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import get_first_day, getdate

from malaysia_workforce.payroll.accumulation import AmbiguousLegacyHistory, accumulate, empty_context
from malaysia_workforce.payroll.profile import (
	SOCSO_EIS_PROFILE_RULE_VERSION,
	SOCSO_EIS_LINDUNG_PROFILE,
	STANDARD_PAYROLL_PROFILE,
	STATUTORY_PROFILE_FIELD,
	normalize_statutory_profile,
	scheme_applies,
)
from malaysia_workforce.payroll.tax_validation import canonical_relief_code
from malaysia_workforce.payroll.validation import (
	hrd_registration_issues,
	lindung_payroll_issues,
	pcb_category_number,
	pcb_gate_issues,
)
from malaysia_workforce.statutory.calculators import (
	calculate_eis,
	calculate_epf,
	calculate_hrd_levy,
	calculate_pcb,
	calculate_socso,
	determine_category,
	determine_socso_category,
	is_eis_age_eligible,
)
from malaysia_workforce.statutory.common import PCBInput, ZERO, ContributionResult, decimal, money
from malaysia_workforce.statutory.rule_pack import RULE_PACK, assert_rule_pack_covers

# Deductions this app owns and rewrites on every calculation. Zakat is deliberately
# excluded: it is an ordinary Salary Structure or Additional Salary deduction that HRMS
# already maintains, and re-appending it here duplicated an Additional Salary zakat row.
MANAGED_DEDUCTIONS = {
	"EPF Employee", "SOCSO Employee", "SKBBK Employee", "EIS Employee", "PCB", "CP38"
}


def _age(date_of_birth, on_date) -> int:
	born, current = getdate(date_of_birth), getdate(on_date)
	return current.year - born.year - ((current.month, current.day) < (born.month, born.day))


def _contract(employee: str, on_date):
	rows = frappe.get_all(
		"Contract",
		filters={"party_type": "Employee", "party_name": employee, "status": "Active", "start_date": ["<=", on_date]},
		fields=["name", "start_date", "end_date", "custom_malaysia_wage_basis", "custom_malaysia_work_classification", "custom_contract_wage_rate",
			"custom_normal_hours_per_day", "custom_normal_hours_per_week", "custom_comparable_full_time_hours",
			"custom_comparable_full_time_hours_per_day",
			"custom_rest_day", "custom_overtime_eligible"],
		order_by="start_date desc",
	)
	for row in rows:
		if not row.end_date or getdate(row.end_date) >= getdate(on_date):
			return row
	frappe.throw(_("Employee {0} has no active ERPNext Contract for this payroll period.").format(employee))


def _component_metadata(names: set[str]) -> dict[str, dict]:
	if not names:
		return {}
	return {
		row.name: row
		for row in frappe.get_all(
			"Salary Component", filters={"name": ["in", list(names)]},
			fields=["name", "salary_component_abbr", "depends_on_payment_days", "exempted_from_income_tax",
				"do_not_include_in_total", "statistical_component", "custom_include_in_epf_wages",
				"custom_include_in_socso_wages", "custom_include_in_eis_wages",
				"custom_include_in_hrd_levy_wages", "custom_pcb_treatment"]
		)
	}


def _classify(doc, *, require_pcb_treatment: bool = True) -> dict[str, Decimal]:
	meta = _component_metadata({row.salary_component for row in doc.earnings})
	bases = {key: ZERO for key in (
		"gross", "epf_regular", "epf_additional", "socso", "eis", "hrd", "pcb_regular", "pcb_additional"
	)}
	for row in doc.earnings:
		amount = decimal(row.amount)
		info = meta.get(row.salary_component, {})
		is_payable = not info.get("statistical_component") and not info.get("do_not_include_in_total")
		if is_payable:
			bases["gross"] += amount
		treatment = info.get("custom_pcb_treatment")
		if amount and is_payable and require_pcb_treatment and not treatment:
			frappe.throw(
				_("Earning component {0} has no Statutory Treatment. Select its PCB Treatment before processing payroll.").format(
					row.salary_component
				)
			)
		kind = "additional" if treatment == "Additional Remuneration" else "regular"
		if info.get("custom_include_in_epf_wages"):
			bases[f"epf_{kind}"] += amount
		if info.get("custom_include_in_socso_wages"):
			bases["socso"] += amount
		if info.get("custom_include_in_eis_wages"):
			bases["eis"] += amount
		if info.get("custom_include_in_hrd_levy_wages"):
			bases["hrd"] += amount
		if treatment == "Regular Remuneration":
			bases["pcb_regular"] += amount
		elif treatment == "Additional Remuneration":
			bases["pcb_additional"] += amount
	return {key: money(value) for key, value in bases.items()}


def _prior_results(doc) -> dict:
	year_start = date(getdate(doc.end_date).year, 1, 1)
	month_start = getdate(get_first_day(doc.end_date))
	slips = frappe.get_all(
		"Salary Slip",
		filters={"employee": doc.employee, "company": doc.company, "docstatus": 1,
			"end_date": ["between", [year_start, doc.end_date]], "name": ["!=", doc.name or ""]},
		fields=["name", "end_date"], order_by="end_date, name",
	)
	context = empty_context()
	if not slips:
		return context
	end_dates = {row.name: getdate(row.end_date) for row in slips}
	rows = frappe.get_all(
		"Malaysia Statutory Result",
		filters={"parent": ["in", list(end_dates)], "parenttype": "Salary Slip"},
		fields=["parent", "scheme", "wage_base", "slip_wages", "per_slip_wages_recorded", "regular_wages", "additional_wages",
			"employee_amount", "employer_amount", "extra_employee_amount"],
	)
	try:
		return accumulate(context, rows, end_dates=end_dates, month_start=month_start)
	except AmbiguousLegacyHistory as exc:
		frappe.throw(
			_(
				"Salary Slips {0} for {1} were calculated by an earlier build that stored only the cumulative monthly wage base. "
				"{2} contributions for this month cannot be calculated without overstating the month's wages. Amend those slips "
				"so they are recalculated before running payroll."
			).format(", ".join(exc.parents), doc.employee, ", ".join(exc.schemes))
		)


def _relief_bucket(out: dict, *, code: str, amount: Decimal, claim_month: int, month: int, declaration: str) -> None:
	"""Accumulate one declared relief into the LHDN prior/current buckets.

	C11 is split on the 2026 TP1 form into C11A (voluntary EPF, limited to RM4,000
	*including* compulsory EPF) and C11B (life insurance/takaful and additional
	voluntary EPF, limited to RM3,000). A lump C11 claim cannot be allocated between
	the two sublimits without guessing, so it is rejected rather than apportioned.
	"""
	if code == "C11":
		frappe.throw(
			_("{0} claims the retired lump-sum code C11. Amend it and split the amount between C11A (voluntary EPF, RM4,000 including compulsory EPF) and C11B (life insurance/takaful or additional voluntary EPF, RM3,000) before payroll.").format(
				declaration
			)
		)
	key = "prior" if claim_month < month else "current"
	if code == "C11A":
		out[f"{key}_c11_epf"] += amount
	elif code == "C11B":
		out[f"{key}_c11_life"] += amount
	else:
		out[f"{key}_tp1"] += amount


def _declarations(employee: str, company: str, year: int, month: int) -> dict[str, Decimal]:
	out = {
		key: ZERO
		for key in (
			"tp3_gross", "tp3_epf", "tp3_pcb", "tp3_zakat", "tp3_reliefs",
			"prior_tp1", "current_tp1", "prior_c11_epf", "current_c11_epf",
			"prior_c11_life", "current_c11_life",
		)
	}
	tp3_rows = frappe.get_all(
		"Malaysia Previous Employment TP3",
		filters={"employee": employee, "company": company, "tax_year": year, "docstatus": 1},
		fields=["name", "gross_normal_remuneration", "gross_additional_remuneration", "epf_contribution", "mtd_paid", "zakat_paid", "optional_reliefs"],
	)
	for row in tp3_rows:
		if decimal(row.optional_reliefs):
			frappe.throw(
				_("TP3 {0} contains a legacy lump-sum relief. Amend it and itemise the official TP1 relief codes before payroll.").format(row.name)
			)
		out["tp3_gross"] += decimal(row.gross_normal_remuneration) + decimal(row.gross_additional_remuneration)
		out["tp3_epf"] += decimal(row.epf_contribution)
		out["tp3_pcb"] += decimal(row.mtd_paid)
		out["tp3_zakat"] += decimal(row.zakat_paid)
	if tp3_rows:
		for row in frappe.get_all(
			"Malaysia Tax Relief Claim",
			filters={"parent": ["in", [item.name for item in tp3_rows]], "parenttype": "Malaysia Previous Employment TP3"},
			fields=["parent", "relief_code", "amount", "claim_month"],
		):
			claim_month = int(row.claim_month or 0)
			if claim_month <= month:
				_relief_bucket(
					out,
					code=canonical_relief_code(row.relief_code),
					amount=decimal(row.amount),
					claim_month=claim_month,
					month=month,
					declaration=_("TP3 {0}").format(row.parent),
				)
	name = frappe.db.get_value(
		"Malaysia Tax Declaration TP1",
		{"employee": employee, "company": company, "tax_year": year, "docstatus": 1},
		"name", order_by="declaration_date desc, modified desc",
	)
	if name:
		for row in frappe.get_all(
			"Malaysia Tax Relief Claim", filters={"parent": name},
			fields=["relief_code", "amount", "claim_month"],
		):
			claim_month = int(row.claim_month or 0)
			if claim_month <= month:
				_relief_bucket(
					out,
					code=canonical_relief_code(row.relief_code),
					amount=decimal(row.amount),
					claim_month=claim_month,
					month=month,
					declaration=_("TP1 {0}").format(name),
				)
	return out


def _append_deduction(doc, component: str, amount: Decimal):
	amount = money(amount)
	if amount <= ZERO:
		return
	meta = frappe.db.get_value(
		"Salary Component", component,
		["salary_component_abbr", "depends_on_payment_days", "exempted_from_income_tax", "do_not_include_in_total", "statistical_component"], as_dict=True,
	)
	if not meta:
		frappe.throw(_("Required Salary Component {0} is missing.").format(component))
	doc.append("deductions", {"salary_component": component, "abbr": meta.salary_component_abbr,
		"amount": float(amount), "default_amount": float(amount), "depends_on_payment_days": meta.depends_on_payment_days,
		"exempted_from_income_tax": meta.exempted_from_income_tax, "do_not_include_in_total": meta.do_not_include_in_total,
		"statistical_component": meta.statistical_component})


def _cp38_amount(directive_amount, monthly_deduction, total_paid, already_deducted) -> Decimal:
	remaining = max(decimal(directive_amount) - decimal(total_paid), ZERO)
	monthly_remaining = max(decimal(monthly_deduction) - decimal(already_deducted), ZERO)
	return money(min(monthly_remaining, remaining))


def _effective_cp38_directive(employee: str, company: str, on_date, fields: list[str]):
	"""Resolve the one CP38 Directive in force on a date, deterministically."""
	row = frappe.db.get_value(
		"Malaysia CP38 Directive",
		{"employee": employee, "company": company, "docstatus": 1, "effective_from": ["<=", on_date]},
		fields, as_dict=True,
		order_by="effective_from desc, creation desc",
	)
	if not row or (row.effective_to and getdate(row.effective_to) < getdate(on_date)):
		return None
	return row


def _cp38(employee: str, company: str, on_date, already_deducted: Decimal) -> Decimal:
	row = _effective_cp38_directive(
		employee, company, on_date, ["name", "directive_amount", "monthly_deduction", "effective_to"]
	)
	if not row:
		return ZERO
	total_paid = frappe.db.sql(
		"""select coalesce(sum(sd.amount), 0) from `tabSalary Detail` sd
		inner join `tabSalary Slip` ss on ss.name=sd.parent
		where ss.employee=%s and ss.company=%s and ss.docstatus=1 and sd.parentfield='deductions'
		and sd.salary_component='CP38' and ss.end_date <= %s""",
		(employee, company, on_date),
	)[0][0]
	return _cp38_amount(row.directive_amount, row.monthly_deduction, total_paid, already_deducted)


def refresh_cp38_directive_after_submit(doc, method=None):
	if not any(row.salary_component == "CP38" and decimal(row.amount) > ZERO for row in doc.deductions):
		return
	row = _effective_cp38_directive(doc.employee, doc.company, doc.end_date, ["name", "effective_to"])
	if not row:
		return
	from malaysia_workforce.malaysia_workforce.doctype.malaysia_cp38_directive.malaysia_cp38_directive import (
		refresh_cp38_balance,
	)

	refresh_cp38_balance(row.name)


def _result(result: ContributionResult, *, regular=ZERO, additional=ZERO, slip_wages=None) -> dict:
	contribution = money(regular) + money(additional) if slip_wages is None else money(slip_wages)
	return {
		"scheme": result.scheme, "applicable": int(result.applicable),
		"wage_base": float(money(result.wage_base)), "slip_wages": float(contribution),
		"per_slip_wages_recorded": 1,
		"regular_wages": float(money(regular)),
		"additional_wages": float(money(additional)), "employee_amount": float(money(result.employee)),
		"employer_amount": float(money(result.employer)), "extra_employee_amount": float(money(result.extra_employee)),
		"category": result.category, "rule_version": result.rule_version,
		"explanation": "\n".join(result.explanation),
	}


def _not_applicable(scheme: str, wage_base=ZERO, explanation: str = "") -> ContributionResult:
	return ContributionResult(
		scheme=scheme,
		wage_base=money(wage_base),
		applicable=False,
		rule_version=SOCSO_EIS_PROFILE_RULE_VERSION,
		explanation=(explanation or "The Employee's Statutory Profile does not include this scheme.",),
	)


def _delta(total: ContributionResult, employee=ZERO, employer=ZERO, extra=ZERO) -> ContributionResult:
	return ContributionResult(total.scheme, total.wage_base, money(total.employee - employee),
		money(total.employer - employer), money(total.extra_employee - extra), total.applicable,
		total.category, total.rule_version, total.explanation + ("Current amount is the month total less prior submitted slips.",))


def apply_malaysia_statutory_calculations(doc, method=None):
	if not frappe.db.get_value("Company", doc.company, "custom_enable_malaysia_payroll"):
		return
	employee = frappe.db.get_value(
		"Employee", doc.employee,
		["custom_malaysia_citizenship_status", "date_of_birth", "relieving_date",
			"custom_pcb_resident", "custom_pcb_category",
			STATUTORY_PROFILE_FIELD,
			"custom_pcb_child_units", "custom_pcb_individual_disabled", "custom_pcb_spouse_disabled",
		 "custom_lindung_participation", "custom_lindung_registration_date", "custom_lindung_effective_from",
		 "custom_lindung_evidence", "custom_lindung_multiple_employers"], as_dict=True,
	)
	if not employee or employee.custom_malaysia_citizenship_status not in {"Malaysian Citizen", "Permanent Resident"}:
		frappe.throw(_("Employee {0} is outside the supported statutory payroll scope.").format(doc.employee))
	profile = normalize_statutory_profile(employee.get(STATUTORY_PROFILE_FIELD))
	if profile not in {STANDARD_PAYROLL_PROFILE, SOCSO_EIS_LINDUNG_PROFILE}:
		frappe.throw(_("Employee {0} has an invalid Statutory Profile.").format(doc.employee))
	assert_rule_pack_covers(doc.end_date)
	if not employee.date_of_birth:
		frappe.throw(_("Date of Birth is missing."))
	age = _age(employee.date_of_birth, doc.end_date)
	lindung_issues = lindung_payroll_issues(employee)
	if lindung_issues:
		frappe.throw("<br>".join(lindung_issues))
	pcb_issues = pcb_gate_issues(employee, profile, doc.end_date)
	if pcb_issues:
		frappe.throw("<br>".join(pcb_issues))
	hrd_issues = hrd_registration_issues(doc.company, doc.end_date)
	if hrd_issues:
		frappe.throw("<br>".join(hrd_issues))
	contract = _contract(doc.employee, doc.end_date)
	from malaysia_workforce.payroll.wages import validate_minimum_wage
	wage_rate = contract.custom_contract_wage_rate
	if contract.custom_malaysia_wage_basis == "Monthly":
		wage_rate = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": doc.employee, "docstatus": 1, "from_date": ["<=", doc.end_date]},
			"base",
			order_by="from_date desc, creation desc",
		)
		if wage_rate is None:
			frappe.throw(_("Employee {0} has no submitted Salary Structure Assignment for the payroll date.").format(doc.employee))
	employee_count = frappe.db.count("Employee", {"company": doc.company, "status": "Active"})
	validate_minimum_wage(
		contract.custom_malaysia_wage_basis,
		wage_rate,
		contract.custom_normal_hours_per_day,
		getdate(doc.end_date),
		employee_count=employee_count,
	)
	current = _classify(doc, require_pcb_treatment=scheme_applies(profile, "PCB"))
	history = _prior_results(doc)
	month = {key: money(current[key] + history["same"].get(key, ZERO)) for key in current if key != "gross"}
	declarations = (
		_declarations(doc.employee, doc.company, getdate(doc.end_date).year, getdate(doc.end_date).month)
		if scheme_applies(profile, "PCB")
		else {key: ZERO for key in ("tp3_gross", "tp3_epf", "tp3_pcb", "tp3_zakat", "tp3_reliefs", "prior_tp1", "current_tp1")}
	)
	if not scheme_applies(profile, "EPF"):
		epf = _not_applicable("EPF", current["epf_regular"] + current["epf_additional"])
	else:
		epf_category = determine_category(citizenship_status=employee.custom_malaysia_citizenship_status, age=age)
		epf_total = calculate_epf(month["epf_regular"] + month["epf_additional"], epf_category)
		epf = _delta(epf_total, history["same_employee"]["EPF"], history["same_employer"]["EPF"])
	socso_total = calculate_socso(
		month["socso"],
		determine_socso_category(age),
		contribution_date=getdate(doc.end_date),
		lindung_participation=employee.custom_lindung_participation,
		lindung_effective_from=(
			getdate(employee.custom_lindung_effective_from) if employee.custom_lindung_effective_from else None
		),
	)
	socso = _delta(socso_total, history["same_employee"]["SOCSO"], history["same_employer"]["SOCSO"], history["same_employee"]["SKBBK"])
	if is_eis_age_eligible(age):
		eis_total = calculate_eis(month["eis"])
		eis = _delta(eis_total, history["same_employee"]["EIS"], history["same_employer"]["EIS"])
	else:
		eis = ContributionResult("EIS", month["eis"], applicable=False, explanation=("Employee is outside the EIS age band (18 up to but not including 60).",))
	company = frappe.get_cached_doc("Company", doc.company)
	if not scheme_applies(profile, "HRD Corp"):
		hrd = _not_applicable("HRD Corp", current["hrd"])
	else:
		hrd_class = company.get("custom_hrd_registration_class") or "Not Registered"
		hrd_rate = Decimal("1") if hrd_class == "Compulsory (1%)" else Decimal("0.5")
		hrd_effective = company.get("custom_hrd_effective_from")
		hrd_registered = bool(
			hrd_class != "Not Registered"
			and hrd_effective
			and getdate(hrd_effective) <= getdate(doc.end_date)
			and employee.custom_malaysia_citizenship_status == "Malaysian Citizen"
		)
		hrd_total = calculate_hrd_levy(month["hrd"], hrd_rate, registered=hrd_registered)
		hrd = _delta(hrd_total, employer=history["same_employer"]["HRD Corp"])

	# Zakat remains an ordinary Frappe HR deduction configured on the Salary
	# Structure or Additional Salary. We only use it as the statutory PCB rebate.
	# PCB consumes epf_category / epf_total from the EPF calculation above, so
	# it is gated on both schemes — a PCB-on/EPF-off profile would otherwise
	# raise UnboundLocalError.
	if scheme_applies(profile, "PCB") and scheme_applies(profile, "EPF"):
		zakat = money(sum((decimal(row.amount) for row in doc.deductions if row.salary_component == "Zakat"), ZERO))
		month_zakat = money(history["same_employee"]["Zakat"] + zakat)
		normal_epf = calculate_epf(month["epf_regular"], epf_category).employee
		additional_epf = max(epf_total.employee - normal_epf, ZERO)
		pcb_args = PCBInput(
			month=getdate(doc.end_date).month, resident=bool(employee.custom_pcb_resident),
			category=pcb_category_number(employee.custom_pcb_category), current_normal_gross=month["pcb_regular"],
			current_additional_gross=month["pcb_additional"],
			prior_gross=history["prior_gross"] + declarations["tp3_gross"],
			prior_epf_relief=history["prior_epf"] + declarations["tp3_epf"],
			current_normal_epf=normal_epf, current_additional_epf=additional_epf,
			prior_optional_reliefs=declarations["tp3_reliefs"] + declarations["prior_tp1"],
			current_optional_reliefs=declarations["current_tp1"],
			prior_c11_epf=declarations["prior_c11_epf"], current_c11_epf=declarations["current_c11_epf"],
			prior_c11_life=declarations["prior_c11_life"], current_c11_life=declarations["current_c11_life"],
			prior_zakat=history["prior_zakat"] + declarations["tp3_zakat"], current_zakat=month_zakat,
			prior_mtd=history["prior_pcb"] + declarations["tp3_pcb"], child_units=decimal(employee.custom_pcb_child_units),
			individual_disabled=bool(employee.custom_pcb_individual_disabled), spouse_disabled=bool(employee.custom_pcb_spouse_disabled),
			estimated_future_normal_gross=month["pcb_regular"],
		)
		pcb_total = calculate_pcb(pcb_args)
		pcb_amount = money(max(pcb_total.payable - history["same_employee"]["PCB"], ZERO))
		pcb = ContributionResult("PCB", current["pcb_regular"] + current["pcb_additional"], employee=pcb_amount,
			rule_version=pcb_total.rule_version, explanation=pcb_total.explanation)
		cp38 = _cp38(doc.employee, doc.company, doc.end_date, history["same_employee"]["CP38"])
	else:
		zakat = ZERO
		pcb = _not_applicable("PCB", current["pcb_regular"] + current["pcb_additional"])
		cp38 = ZERO

	doc.set("deductions", [row for row in doc.deductions if row.salary_component not in MANAGED_DEDUCTIONS])
	_append_deduction(doc, "EPF Employee", epf.employee)
	_append_deduction(doc, "SOCSO Employee", socso.employee)
	_append_deduction(doc, "SKBBK Employee", socso.extra_employee)
	_append_deduction(doc, "EIS Employee", eis.employee)
	if scheme_applies(profile, "PCB"):
		_append_deduction(doc, "PCB", pcb.employee)
		_append_deduction(doc, "CP38", cp38)
	else:
		# Zakat is a salary deduction the app does not own, but a profile that excludes
		# tax deductions must not inherit a Zakat row from a shared Salary Structure.
		doc.set("deductions", [row for row in doc.deductions if row.salary_component != "Zakat"])

	results = [
		_result(epf, regular=current["epf_regular"], additional=current["epf_additional"]),
		_result(socso, regular=current["socso"]),
		_result(eis, regular=current["eis"]),
		_result(hrd, regular=current["hrd"]),
		_result(pcb, regular=current["pcb_regular"], additional=current["pcb_additional"]),
		_result(
			_not_applicable("CP38", current["gross"]) if not scheme_applies(profile, "CP38")
			else ContributionResult("CP38", current["gross"], employee=cp38, rule_version="LHDN-CP38")
		),
		_result(
			_not_applicable("Zakat", current["gross"]) if not scheme_applies(profile, "Zakat")
			else ContributionResult("Zakat", current["gross"], employee=zakat, rule_version="LHDN-ZAKAT-REBATE")
		),
	]
	doc.set("custom_malaysia_statutory_results", [])
	for row in results:
		doc.append("custom_malaysia_statutory_results", row)
	doc.custom_malaysia_statutory_profile = profile
	doc.custom_malaysia_rule_pack = RULE_PACK
	# HRMS has already calculated the slip (including Salary Structure components) before
	# this hook runs. Calling calculate_net_pay() again would re-apply structure components
	# that share a managed name and silently replace the statutory amounts, so only the
	# totals are recomputed here.
	doc.set_net_pay()
	doc.compute_year_to_date()
	doc.compute_month_to_date()
	doc.compute_component_wise_year_to_date()


def validate_statutory_profile_snapshot(doc, method=None):
	if not frappe.db.get_value("Company", doc.company, "custom_enable_malaysia_payroll"):
		return
	employee = frappe.db.get_value(
		"Employee", doc.employee,
		[STATUTORY_PROFILE_FIELD, "custom_pcb_resident", "relieving_date"], as_dict=True,
	)
	current = normalize_statutory_profile(employee.get(STATUTORY_PROFILE_FIELD))
	if normalize_statutory_profile(doc.get(STATUTORY_PROFILE_FIELD)) != current:
		frappe.throw(_("This Salary Slip uses an older Statutory Profile. Open and save it again before submitting."))
	# Frappe submit() sets docstatus=1 before validate runs, so a slip calculated while still
	# compliant (e.g. still resident, or employed) must have these fail-closed gates re-checked
	# here in case a disqualifying change happened after the last calculate.
	assert_rule_pack_covers(doc.end_date)
	pcb_issues = pcb_gate_issues(employee, current, doc.end_date)
	if pcb_issues:
		frappe.throw("<br>".join(pcb_issues))


def protect_filed_salary_slip(doc, method=None):
	filings = frappe.get_all(
		"Malaysia Statutory Filing",
		filters={"company": doc.company, "period_start": ["<=", doc.end_date], "period_end": [">=", doc.start_date],
			"docstatus": 1},
		pluck="name",
	)
	if filings and frappe.db.exists("Malaysia Filing Employee", {"parent": ["in", filings], "employee": doc.employee}):
		frappe.throw(_("This Salary Slip is included in a submitted statutory filing. Create an amendment instead."))

from __future__ import annotations

import csv
import io
from collections import defaultdict
from decimal import Decimal

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
from malaysia_workforce.statutory.exporters.epf_csv import EPFCSVRecord, generate_epf_csv
from malaysia_workforce.statutory.exporters.lhdn_pcb import LHDNPCBRecord, generate_lhdn_pcb_file
from malaysia_workforce.statutory.exporters.perkeso_combined import PERKESOCombinedRecord, generate_perkeso_combined_file
from malaysia_workforce.statutory.rule_pack import RULE_PACK
from malaysia_workforce.utils import sha256_bytes, stable_json

COMPANY_SERIALIZER_FIELDS = (
	"company_name",
	"custom_company_registration_number",
	"custom_epf_employer_number",
	"custom_socso_employer_code",
	"custom_lhdn_hq_number",
	"custom_lhdn_employer_number",
	"custom_hrd_registration_class",
	"custom_hrd_registration_number",
)
EMPLOYEE_SERIALIZER_FIELDS = (
	"employee_name",
	"employee_number",
	"custom_nric",
	"passport_number",
	"custom_tax_identification_number",
	"custom_epf_member_number",
	STATUTORY_PROFILE_FIELD,
)


def _salary_slip_profile(value) -> str:
	profile = normalize_statutory_profile(value)
	if profile not in {STANDARD_PAYROLL_PROFILE, SOCSO_EIS_LINDUNG_PROFILE}:
		frappe.throw(_("A submitted Salary Slip has an unsupported Statutory Profile."))
	return profile


def _result_rows(filing) -> list:
	slips = frappe.get_all(
		"Salary Slip",
		filters={"company": filing.company, "docstatus": 1,
			"end_date": ["between", [filing.period_start, filing.period_end]]},
		fields=["name", "employee", "employee_name", STATUTORY_PROFILE_FIELD],
		order_by="employee, end_date, name",
	)
	if not slips:
		frappe.throw(_("No submitted Salary Slips exist in this filing period."))
	parents = {row.name: row for row in slips}
	results = frappe.get_all(
		"Malaysia Statutory Result", filters={"parent": ["in", list(parents)], "parenttype": "Salary Slip"},
		fields=["parent", "scheme", "wage_base", "slip_wages", "per_slip_wages_recorded", "regular_wages", "additional_wages",
			"employee_amount", "employer_amount", "extra_employee_amount", "applicable", "rule_version"],
		order_by="parent, scheme, name",
	)
	return [
		{
			**dict(row),
			"employee": parents[row.parent].employee,
			"employee_name": parents[row.parent].employee_name,
			"profile": _salary_slip_profile(parents[row.parent].get(STATUTORY_PROFILE_FIELD)),
		}
		for row in results
	]


def _schemes(filing) -> set[str]:
	if filing.authority == "EPF": return {"EPF"}
	if filing.authority == "PERKESO": return {"SOCSO", "EIS"}
	if filing.authority == "LHDN": return {"PCB", "CP38"}
	if filing.authority == "HRD Corp": return {"HRD Corp"}
	return set()


def _serializable_amount(value) -> str:
	return format(Decimal(str(value or 0)), "f")


def _source_payload(filing, company_identity: dict, items: list[dict]) -> dict:
	"""Return every value that can influence an authority file."""
	return {
		"authority": filing.authority,
		"company": filing.company,
		"period_start": str(filing.period_start),
		"period_end": str(filing.period_end),
		"company_identity": {key: str(company_identity.get(key) or "") for key in COMPANY_SERIALIZER_FIELDS},
		"employees": [
			{
				"employee": item["employee"],
				"employee_name": str(item["employee_name"] or ""),
				"identity": {
					key: str(item["identity"].get(key) or "") for key in EMPLOYEE_SERIALIZER_FIELDS
				},
				"profile": item["profile"],
				"wages": _serializable_amount(item["wages"]),
				"employee_amount": _serializable_amount(item["employee_amount"]),
				"employer_amount": _serializable_amount(item["employer_amount"]),
				"additional_amount": _serializable_amount(item["additional_amount"]),
				"versions": sorted(item["versions"]),
				"schemes": {
					scheme: {key: _serializable_amount(value) for key, value in sorted(amounts.items())}
					for scheme, amounts in sorted(item["schemes"].items())
				},
			}
			for item in sorted(items, key=lambda value: value["employee"])
		],
	}


WAGE_SCHEME_BY_AUTHORITY = {
	"EPF": "EPF",
	"PERKESO": "SOCSO",
	"LHDN": "PCB",
	"HRD Corp": "HRD Corp",
}


def _per_slip_wages(row, duplicate_keys: set[tuple[str, str]]) -> Decimal:
	"""Wage contributed by one slip, never the cumulative month base.

	Rows written before slip_wages existed only carry the cumulative month base. That is
	usable when the employee has a single slip for the scheme in the period, and
	ambiguous otherwise, so a multi-slip legacy period fails closed instead of guessing.
	"""
	if row.get("per_slip_wages_recorded"):
		return Decimal(str(row["slip_wages"] or 0))
	base = Decimal(str(row["wage_base"] or 0))
	if base and (row["employee"], row["scheme"]) in duplicate_keys:
		frappe.throw(
			_(
				"Salary Slip {0} was calculated by an earlier build that stored only the cumulative monthly wage base. "
				"{1} has more than one {2} slip in this period, so the authority wage cannot be derived without guessing. "
				"Amend the affected slips (or prepare a single-slip period) before preparing this filing."
			).format(row["parent"], row["employee"], row["scheme"])
		)
	return base


def _aggregate(filing) -> tuple[list[dict], str, dict]:
	rows = [
		row
		for row in _result_rows(filing)
		if row["scheme"] in _schemes(filing)
		and row.get("applicable", 1)
		and scheme_applies(row["profile"], row["scheme"])
	]
	if not rows:
		frappe.throw(_("No applicable {0} statutory results exist in this period.").format(filing.authority))
	counts: dict[tuple[str, str], int] = defaultdict(int)
	for row in rows:
		counts[(row["employee"], row["scheme"])] += 1
	duplicate_keys = {key for key, count in counts.items() if count > 1}
	items: dict[str, dict] = {}
	for row in rows:
		item = items.setdefault(row["employee"], {"employee": row["employee"], "employee_name": row["employee_name"],
			"profile": row.get("profile") or "Standard Payroll",
			"wages": Decimal("0"), "employee_amount": Decimal("0"), "employer_amount": Decimal("0"),
			"additional_amount": Decimal("0"), "versions": set(), "schemes": defaultdict(lambda: {"wages": Decimal("0"),
				"employee": Decimal("0"), "employer": Decimal("0"), "extra": Decimal("0")})})
		bucket = item["schemes"][row["scheme"]]
		bucket["wages"] += _per_slip_wages(row, duplicate_keys)
		bucket["employee"] += Decimal(str(row["employee_amount"] or 0))
		bucket["employer"] += Decimal(str(row["employer_amount"] or 0))
		bucket["extra"] += Decimal(str(row["extra_employee_amount"] or 0))
		item["employee_amount"] += Decimal(str(row["employee_amount"] or 0))
		item["employer_amount"] += Decimal(str(row["employer_amount"] or 0))
		item["additional_amount"] += Decimal(str(row["extra_employee_amount"] or 0))
		item["versions"].add(row["rule_version"] or "")
	wage_scheme = WAGE_SCHEME_BY_AUTHORITY.get(filing.authority)
	for item in items.values():
		item["wages"] = item["schemes"].get(wage_scheme, {}).get("wages", Decimal("0"))
	item_rows = list(items.values())
	for item in item_rows:
		item["identity"] = dict(_employee(item["employee"]) or {})
	company_identity = dict(
		frappe.db.get_value("Company", filing.company, COMPANY_SERIALIZER_FIELDS, as_dict=True) or {}
	)
	source = sha256_bytes(stable_json(_source_payload(filing, company_identity, item_rows)).encode())
	return item_rows, source, company_identity


def _employee(employee: str):
	return frappe.db.get_value("Employee", employee, EMPLOYEE_SERIALIZER_FIELDS, as_dict=True)


def _render(filing, items: list[dict], company: dict) -> tuple[str, bytes]:
	month = getdate(filing.period_end)
	if filing.authority == "EPF":
		records = []
		for item in items:
			emp = item["identity"]
			records.append(EPFCSVRecord(emp.get("custom_epf_member_number"), emp.get("custom_nric") or emp.get("passport_number"),
				emp.get("employee_name"), item["wages"], item["employer_amount"], item["employee_amount"]))
		return f"epf-preparation-{month:%Y-%m}.csv", generate_epf_csv(records)
	if filing.authority == "PERKESO":
		records = []
		for item in items:
			emp = item["identity"]; socso = item["schemes"]["SOCSO"]; eis = item["schemes"]["EIS"]
			records.append(PERKESOCombinedRecord(company.get("custom_socso_employer_code"), company.get("custom_company_registration_number"),
				emp.get("custom_nric") or emp.get("passport_number"), emp.get("employee_name"), month.strftime("%m%Y"), socso["wages"],
				socso["employer"], socso["employee"], eis["employer"], eis["employee"], socso["extra"]))
		return f"perkeso-{month:%Y-%m}.txt", generate_perkeso_combined_file(records)
	if filing.authority == "LHDN":
		records = []
		for item in items:
			emp = item["identity"]; pcb = item["schemes"]["PCB"]; cp38 = item["schemes"]["CP38"]
			records.append(LHDNPCBRecord(tin=emp.get("custom_tax_identification_number"), name=emp.get("employee_name"),
				new_ic=emp.get("custom_nric"), passport=emp.get("passport_number"), country_code="MY" if emp.get("passport_number") else "",
				mtd_amount=pcb["employee"], cp38_amount=cp38["employee"], employee_number=emp.get("employee_number") or item["employee"]))
		return f"lhdn-pcb-{month:%Y-%m}.txt", generate_lhdn_pcb_file(hq_number=company.get("custom_lhdn_hq_number"),
			employer_number=company.get("custom_lhdn_employer_number"), year=month.year, month=month.month, records=records)
	if filing.authority == "HRD Corp":
		stream = io.StringIO(newline="")
		writer = csv.writer(stream, lineterminator="\r\n")
		writer.writerow(["HRD Corp Registration Class", company.get("custom_hrd_registration_class") or ""])
		writer.writerow(["HRD Corp Registration Number", company.get("custom_hrd_registration_number") or ""])
		writer.writerow([])
		writer.writerow(["Employee", "NRIC", "Employee Name", "Leviable Wages", "Employer Levy"])
		for item in items:
			emp = item["identity"]
			writer.writerow(
				[
					item["employee"],
					emp.get("custom_nric") or "",
					emp.get("employee_name") or item["employee_name"],
					f"{item['wages']:.2f}",
					f"{item['employer_amount']:.2f}",
				]
			)
		return f"hrd-levy-working-paper-{month:%Y-%m}.csv", stream.getvalue().encode("utf-8-sig")
	frappe.throw(_("No reviewed output adapter exists for {0}.").format(filing.authority))


def prepare_filing(filing) -> dict:
	filing.check_permission("write")
	if filing.docstatus != 0:
		frappe.throw(_("Only a draft filing can be prepared."))
	items, source_hash, company_identity = _aggregate(filing)
	if source_hash == filing.source_hash and filing.generated_file and filing.file_hash:
		return {
			"status": "Prepared",
			"employees": len(items),
			"file": filing.generated_file,
			"source_hash": source_hash,
		}
	name, content = _render(filing, items, company_identity)
	filing.set("employee_lines", [])
	for item in items:
		filing.append("employee_lines", {"employee": item["employee"], "employee_name": item["employee_name"],
			"wages": item["wages"], "employee_amount": item["employee_amount"], "employer_amount": item["employer_amount"],
			"additional_amount": item["additional_amount"], "rule_version": ", ".join(sorted(item["versions"]))})
	filing.total_wages = sum((item["wages"] for item in items), Decimal("0"))
	filing.total_employee = sum((item["employee_amount"] for item in items), Decimal("0"))
	filing.total_employer = sum((item["employer_amount"] for item in items), Decimal("0"))
	filing.total_additional = sum((item["additional_amount"] for item in items), Decimal("0"))
	filing.source_hash = source_hash
	filing.rule_pack = RULE_PACK
	for stale_file in frappe.get_all(
		"File",
		filters={"attached_to_doctype": filing.doctype, "attached_to_name": filing.name, "attached_to_field": "generated_file"},
		pluck="name",
	):
		frappe.delete_doc("File", stale_file, ignore_permissions=True)
	file_doc = frappe.get_doc({"doctype": "File", "file_name": name, "content": content, "is_private": 1,
		"attached_to_doctype": filing.doctype, "attached_to_name": filing.name, "attached_to_field": "generated_file"}).save(ignore_permissions=True)
	filing.generated_file = file_doc.file_url; filing.file_hash = sha256_bytes(content); filing.save()
	return {"status": "Prepared", "employees": len(items), "file": filing.generated_file, "source_hash": source_hash}


def scheme_breakdown(filing) -> dict[str, dict[str, Decimal]]:
	"""Scheme-split control totals for the print format, computed at render time.

	`employee_lines` only stores each employee's aggregate, not the per-scheme split, and
	persisting that split would need a schema migration — recompute it here instead from
	`Malaysia Statutory Result` rows scoped to the employees already recorded on this filing.
	"""
	employees = [row.employee for row in (filing.employee_lines or [])]
	if not employees:
		return {}
	slips = frappe.get_all(
		"Salary Slip",
		filters={"company": filing.company, "employee": ["in", employees], "docstatus": 1,
			"end_date": ["between", [filing.period_start, filing.period_end]]},
		pluck="name",
	)
	if not slips:
		return {}
	rows = frappe.get_all(
		"Malaysia Statutory Result",
		filters={"parent": ["in", slips], "parenttype": "Salary Slip", "scheme": ["in", list(_schemes(filing))], "applicable": 1},
		fields=["parent", "scheme", "wage_base", "slip_wages", "per_slip_wages_recorded", "employee_amount", "employer_amount", "extra_employee_amount"],
	)
	slip_employee = {
		name: employee
		for name, employee in frappe.get_all(
			"Salary Slip", filters={"name": ["in", slips]}, fields=["name", "employee"], as_list=True
		)
	}
	counts: dict[tuple[str, str], int] = defaultdict(int)
	for row in rows:
		counts[(slip_employee.get(row.parent), row.scheme)] += 1
	duplicate_keys = {key for key, count in counts.items() if count > 1}
	for row in rows:
		row["employee"] = slip_employee.get(row.parent)
	breakdown: dict[str, dict[str, Decimal]] = {}
	for row in rows:
		bucket = breakdown.setdefault(row.scheme, {
			"wage_base": Decimal("0"), "employee_amount": Decimal("0"),
			"employer_amount": Decimal("0"), "extra_employee_amount": Decimal("0"),
		})
		bucket["wage_base"] += _per_slip_wages(row, duplicate_keys)
		bucket["employee_amount"] += Decimal(str(row.employee_amount or 0))
		bucket["employer_amount"] += Decimal(str(row.employer_amount or 0))
		bucket["extra_employee_amount"] += Decimal(str(row.extra_employee_amount or 0))
	return breakdown


def validate_filing_source(filing) -> None:
	_items, current_hash, _company_identity = _aggregate(filing)
	if current_hash != filing.source_hash:
		frappe.throw(_("Payroll results or filing identifiers changed after preparation. Prepare the filing again."))


def reconcile_filing(filing) -> dict:
	filing.check_permission("write")
	if filing.docstatus != 1:
		frappe.throw(_("Submit the filing before reconciliation."))
	items, current_hash, _company_identity = _aggregate(filing)
	current = sum((item["employee_amount"] + item["employer_amount"] + item["additional_amount"] for item in items), Decimal("0"))
	stored = Decimal(str(filing.total_employee or 0)) + Decimal(str(filing.total_employer or 0)) + Decimal(str(filing.total_additional or 0))
	filing.reconciliation_difference = current - stored
	if current_hash != filing.source_hash:
		frappe.throw(_("Payroll results or filing identifiers changed after preparation. Create an amendment."))
	if filing.reconciliation_difference:
		frappe.throw(_("Filing differs from current Salary Slips by RM {0:.2f}.").format(filing.reconciliation_difference))
	if not filing.submission_evidence:
		frappe.throw(_("Attach portal submission evidence before reconciliation."))
	if filing.authority_status != "Accepted" or not filing.acknowledgement:
		frappe.throw(_("Record Accepted and attach the authority acknowledgement before reconciliation."))
	filing.reconciliation_status = "Reconciled"
	filing.save()
	return {"status": filing.reconciliation_status, "difference": 0}

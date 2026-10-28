from datetime import date
from decimal import Decimal

from malaysia_workforce.payroll.accumulation import accumulate, empty_context


class Row(dict):
	__getattr__ = dict.__getitem__


def result(parent, scheme, *, wage_base="0", slip_wages=None, regular="0", additional="0",
	employee="0", employer="0", extra="0", recorded=None):
	return Row(
		parent=parent,
		scheme=scheme,
		wage_base=Decimal(wage_base),
		slip_wages=Decimal(slip_wages or 0),
		per_slip_wages_recorded=1 if recorded is None and slip_wages is not None else int(recorded or 0),
		regular_wages=Decimal(regular),
		additional_wages=Decimal(additional),
		employee_amount=Decimal(employee),
		employer_amount=Decimal(employer),
		extra_employee_amount=Decimal(extra),
	)


def same_month(rows):
	month_start = date(2026, 9, 1)
	end_dates = {row.parent: date(2026, 9, 30) for row in rows}
	return accumulate(empty_context(), rows, end_dates=end_dates, month_start=month_start)


def test_two_slips_sum_their_own_wage_bases_not_the_cumulative_month_base():
	"""2,000 + 2,000 must be 4,000, not 6,000 (the second row's wage_base)."""
	context = same_month([
		result("SLIP-1", "SOCSO", wage_base="2000", slip_wages="2000", employee="9.75", employer="34.15", extra="14.65"),
		result("SLIP-2", "SOCSO", wage_base="4000", slip_wages="2000", employee="10.00", employer="35.00", extra="15.00"),
	])
	assert context["same"]["socso"] == Decimal("4000.00")
	assert context["same_employee"]["SOCSO"] == Decimal("19.75")
	assert context["same_employee"]["SKBBK"] == Decimal("29.65")


def test_three_slips_do_not_compound():
	"""5,000 + 5,000 + 5,000 is 15,000 even though the stored bases are 5,000, 10,000, 15,000."""
	rows = [
		result("S1", "HRD Corp", wage_base="5000", slip_wages="5000", employer="50"),
		result("S2", "HRD Corp", wage_base="10000", slip_wages="5000", employer="50"),
		result("S3", "HRD Corp", wage_base="15000", slip_wages="5000", employer="50"),
	]
	context = same_month(rows)
	assert context["same"]["hrd"] == Decimal("15000.00")
	assert context["same_employer"]["HRD Corp"] == Decimal("150.00")


def test_epf_uses_per_slip_regular_and_additional_wages():
	context = same_month([
		result("S1", "EPF", wage_base="2000", slip_wages="2000", regular="2000", employee="220", employer="260"),
		result("S2", "EPF", wage_base="4000", slip_wages="2000", regular="2000", employee="220", employer="240"),
	])
	assert context["same"]["epf_regular"] == Decimal("4000.00")
	assert context["same_employee"]["EPF"] == Decimal("440.00")


def test_legacy_row_without_slip_wages_falls_back_to_its_stored_base():
	context = same_month([result("S1", "SOCSO", wage_base="2000", employee="9.75")])
	assert context["same"]["socso"] == Decimal("2000.00")


def test_prior_month_rows_are_kept_out_of_the_same_month_totals():
	month_start = date(2026, 9, 1)
	end_dates = {"AUG": date(2026, 8, 31)}
	rows = [
		result("AUG", "PCB", regular="5000", employee="110"),
		result("AUG", "EPF", employee="550"),
		result("AUG", "SOCSO", wage_base="5000", slip_wages="5000", employee="24.75"),
	]
	context = accumulate(empty_context(), rows, end_dates=end_dates, month_start=month_start)
	assert context["prior_gross"] == Decimal("5000.00")
	assert context["prior_pcb"] == Decimal("110.00")
	assert context["prior_epf"] == Decimal("550.00")
	assert context["same"]["socso"] == Decimal("0.00")

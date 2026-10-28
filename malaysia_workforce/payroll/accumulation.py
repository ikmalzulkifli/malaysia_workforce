"""Same-month / prior-month accumulation of statutory result rows.

Kept free of Frappe imports so the wage-base rules can be tested directly; the
database readers in payroll.salary_slip call into this module.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from malaysia_workforce.statutory.common import ZERO, decimal

SAME_MONTH_BASE_SCHEMES = {"SOCSO", "EIS", "HRD Corp"}


class AmbiguousLegacyHistory(ValueError):
	"""Raised when same-month wage bases cannot be reconstructed without guessing.

	Rows written before the per-slip wage fix store only the cumulative month base.
	Summing two of them double counts the month, so calculation stops instead.
	"""

	def __init__(self, schemes: list[str], parents: list[str]):
		self.schemes = tuple(sorted(schemes))
		self.parents = tuple(sorted(parents))
		super().__init__(
			f"{', '.join(self.schemes)} wage bases for {', '.join(self.parents)} were stored by an "
			"earlier build as cumulative monthly totals and cannot be summed"
		)


def slip_wages(row) -> Decimal:
	"""Wage base contributed by the slip that produced this statutory result row.

	Older rows stored only the cumulative month base in ``wage_base``; new rows also
	store their own contribution in ``slip_wages`` and mark ``per_slip_wages_recorded``.
	Summing ``wage_base`` across slips compounds the month total, so per-slip data is
	used whenever the marker is set.
	"""
	if row.get("per_slip_wages_recorded"):
		return decimal(row.get("slip_wages"))
	return decimal(row.wage_base)


def empty_context() -> dict:
	return {
		"prior_gross": ZERO, "prior_epf": ZERO, "prior_pcb": ZERO, "prior_zakat": ZERO,
		"same": {key: ZERO for key in ("epf_regular", "epf_additional", "socso", "eis", "hrd", "pcb_regular", "pcb_additional")},
		"same_employee": {key: ZERO for key in ("EPF", "SOCSO", "SKBBK", "EIS", "PCB", "CP38", "Zakat")},
		"same_employer": {key: ZERO for key in ("EPF", "SOCSO", "EIS", "HRD Corp")},
	}


def accumulate(context: dict, rows, *, end_dates: dict, month_start) -> dict:
	"""Fold statutory result rows into prior-month and same-month totals.

	``wage_base`` on a row is the cumulative month base used for that slip's contribution
	calculation. It must never be summed across same-month slips; ``slip_wages`` is the
	per-slip contribution to the month and is what these totals use.
	"""
	same_month = [row for row in rows if end_dates[row.parent] >= month_start]
	counts = Counter(row.scheme for row in same_month)
	legacy_parents: dict[str, list[str]] = {}
	for row in same_month:
		if row.scheme in SAME_MONTH_BASE_SCHEMES and not row.get("per_slip_wages_recorded"):
			legacy_parents.setdefault(row.scheme, []).append(row.parent)
	ambiguous = sorted(
		scheme
		for scheme, parents in legacy_parents.items()
		if counts[scheme] > 1
		and any(
			decimal(row.wage_base) > 0
			for row in same_month
			if row.scheme == scheme and not row.get("per_slip_wages_recorded")
		)
	)
	if ambiguous:
		raise AmbiguousLegacyHistory(
			ambiguous, sorted({parent for scheme in ambiguous for parent in legacy_parents[scheme]})
		)

	for row in rows:
		if end_dates[row.parent] < month_start:
			if row.scheme == "PCB":
				context["prior_gross"] += decimal(row.regular_wages) + decimal(row.additional_wages)
				context["prior_pcb"] += decimal(row.employee_amount)
			elif row.scheme == "EPF":
				context["prior_epf"] += decimal(row.employee_amount)
			elif row.scheme == "Zakat":
				context["prior_zakat"] += decimal(row.employee_amount)
			continue
		if row.scheme == "EPF":
			context["same"]["epf_regular"] += decimal(row.regular_wages)
			context["same"]["epf_additional"] += decimal(row.additional_wages)
		elif row.scheme in SAME_MONTH_BASE_SCHEMES:
			context["same"][row.scheme.lower().replace(" corp", "")] += slip_wages(row)
		elif row.scheme == "PCB":
			context["same"]["pcb_regular"] += decimal(row.regular_wages)
			context["same"]["pcb_additional"] += decimal(row.additional_wages)
		if row.scheme in context["same_employee"]:
			context["same_employee"][row.scheme] += decimal(row.employee_amount)
		if row.scheme == "SOCSO":
			# SKBBK is carried on the SOCSO row as extra_employee_amount and is deducted
			# as its own component, so it has to be tracked separately or a second slip
			# in the same month double-charges it.
			context["same_employee"]["SKBBK"] += decimal(row.extra_employee_amount)
		if row.scheme in context["same_employer"]:
			context["same_employer"][row.scheme] += decimal(row.employer_amount)
	return context

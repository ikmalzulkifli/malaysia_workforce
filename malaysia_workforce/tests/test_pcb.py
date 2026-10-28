from datetime import date
from decimal import Decimal

from malaysia_workforce.statutory.calculators.pcb import calculate_pcb, leaver_breaks_annual_projection
from malaysia_workforce.statutory.common import PCBInput


def d(value: str | int | float) -> Decimal:
	return Decimal(str(value))


def test_lhdn_worked_example_january():
	result = calculate_pcb(
		PCBInput(
			month=1,
			resident=True,
			category=3,
			current_normal_gross=d(5500),
			current_normal_epf=d(605),
			child_units=d(3),
		)
	)
	assert result.payable == d("110.00")
	assert result.chargeable_income_normal == d("47000.07")


def test_lhdn_worked_example_february():
	result = calculate_pcb(
		PCBInput(
			month=2,
			resident=True,
			category=3,
			current_normal_gross=d(5500),
			current_normal_epf=d(605),
			prior_gross=d(5500),
			prior_epf_relief=d(605),
			prior_mtd=d(110),
			child_units=d(3),
		)
	)
	assert result.payable == d("110.00")
	assert result.chargeable_income_normal == d("47000.00")


def test_lhdn_worked_example_march_with_tp1_relief():
	result = calculate_pcb(
		PCBInput(
			month=3,
			resident=True,
			category=3,
			current_normal_gross=d(5500),
			current_normal_epf=d(605),
			prior_gross=d(11000),
			prior_epf_relief=d(1210),
			prior_mtd=d("220.00"),
			current_optional_reliefs=d(300),
			child_units=d(3),
		)
	)
	assert result.payable == d("108.20")
	assert result.chargeable_income_normal == d("46700.07")


def test_lhdn_worked_example_april_bonus():
	result = calculate_pcb(
		PCBInput(
			month=4,
			resident=True,
			category=3,
			current_normal_gross=d(5500),
			current_additional_gross=d(8250),
			current_normal_epf=d(605),
			current_additional_epf=d(908),
			prior_gross=d(16500),
			prior_epf_relief=d(1815),
			prior_mtd=d("328.20"),
			prior_optional_reliefs=d(300),
			current_optional_reliefs=d(300),
			child_units=d(3),
		)
	)
	assert result.normal_mtd_after_zakat == d("106.20")
	assert result.additional_mtd == d("727.50")
	assert result.payable == d("833.70")
	assert result.chargeable_income_with_additional == d("54650.00")


def test_zakat_reduces_pcb_in_additional_remuneration_month():
	base = dict(
		month=4, resident=True, category=3, current_normal_gross=d(5500),
		current_additional_gross=d(8250), current_normal_epf=d(605), current_additional_epf=d(908),
		prior_gross=d(16500), prior_epf_relief=d(1815), prior_mtd=d("328.20"),
		prior_optional_reliefs=d(300), current_optional_reliefs=d(300), child_units=d(3),
	)
	without_zakat = calculate_pcb(PCBInput(**base))
	with_current_zakat = calculate_pcb(PCBInput(**base, current_zakat=d(100)))
	with_prior_and_current = calculate_pcb(PCBInput(**base, prior_zakat=d(300), current_zakat=d(100)))
	assert without_zakat.payable == d("833.70")
	assert with_current_zakat.payable == d("733.70")
	# With RM300 of prior zakat the normal MTD falls to 72.90, so RM27.10 of the
	# current RM100 is not absorbed and offsets the additional-remuneration MTD
	# (727.20 - 27.10), matching HASiL's worked table pattern (spec section E.5(ii)).
	assert with_prior_and_current.payable == d("700.10")
	assert with_prior_and_current.zakat_offset_additional == d("27.10")
	assert with_current_zakat.payable < without_zakat.payable
	assert with_prior_and_current.payable < with_current_zakat.payable


def test_nonresident_rate_and_minimum():
	result = calculate_pcb(
		PCBInput(
			month=8,
			resident=False,
			category=1,
			current_normal_gross=d(10000),
		)
	)
	assert result.payable == d("3000.00")


def test_disabled_spouse_relief_gated_on_category_2():
	"""A category 1/3 employee has no spouse relief claimed, so no disabled-spouse relief either."""
	base_args = dict(month=6, resident=True, current_normal_gross=d(8000))
	category_1_not_disabled = calculate_pcb(PCBInput(category=1, spouse_disabled=False, **base_args))
	category_1_disabled = calculate_pcb(PCBInput(category=1, spouse_disabled=True, **base_args))
	category_2_not_disabled = calculate_pcb(PCBInput(category=2, spouse_disabled=False, **base_args))
	category_2_disabled = calculate_pcb(PCBInput(category=2, spouse_disabled=True, **base_args))
	assert category_1_disabled.chargeable_income_normal == category_1_not_disabled.chargeable_income_normal
	assert category_2_disabled.chargeable_income_normal == category_2_not_disabled.chargeable_income_normal - d(6000)


def test_leaver_before_year_end_breaks_projection():
	"""A November leaver still breaks an October slip's projection through December."""
	assert leaver_breaks_annual_projection(date(2026, 11, 15), date(2026, 10, 31)) is True


def test_leaver_on_31_december_does_not_break_projection():
	assert leaver_breaks_annual_projection(date(2026, 12, 31), date(2026, 12, 31)) is False


def test_no_relieving_date_does_not_break_projection():
	assert leaver_breaks_annual_projection(None, date(2026, 6, 30)) is False


def test_relief_code_accepts_codes_and_labels():
	from malaysia_workforce.payroll.tax_validation import canonical_relief_code

	assert canonical_relief_code("C5") == "C5"
	assert canonical_relief_code("C5 - Lifestyle expenses") == "C5"
	assert canonical_relief_code("c16a - First-home") == "C16A"
	assert canonical_relief_code("") == ""


def test_pcb_category_number_accepts_codes_and_labels():
	from malaysia_workforce.payroll.tax_validation import pcb_category_number

	assert pcb_category_number("1") == 1
	assert pcb_category_number("2 - Married, spouse not working") == 2
	assert pcb_category_number("3 - Married, spouse working") == 3
	assert pcb_category_number(None) == 1
	assert pcb_category_number("9") == 1


def test_invalid_month_rejected():
	try:
		calculate_pcb(PCBInput(month=13, resident=True, category=1, current_normal_gross=d(1000)))
	except ValueError as exc:
		assert "month" in str(exc).lower()
	else:
		raise AssertionError("Expected ValueError")


def _c11_input(**overrides):
	"""Married, spouse working (category 3), no children, January, RM2,500 normal pay.

	EPF RM275/month produces K = RM3,300 for the year (275 + 275 x 11), so only
	RM700 of the RM4,000 EPF sublimit is left for a C11A claim.
	"""
	base = dict(
		month=1,
		resident=True,
		category=3,
		current_normal_gross=d(2500),
		current_normal_epf=d(275),
	)
	base.update(overrides)
	return PCBInput(**base)


def test_c11_epf_claim_is_limited_to_the_unused_part_of_the_rm4000_sublimit():
	"""RM4,000 of voluntary EPF cannot be added on top of RM3,300 of compulsory EPF relief."""
	without_c11 = calculate_pcb(_c11_input())
	with_full_c11a = calculate_pcb(_c11_input(current_c11_epf=d(4000)))

	# P = (2,500 - 275) + (2,500 - 275) x 11 - 9,000 = 17,700 before C11.
	assert without_c11.chargeable_income_normal == d("17700.00")
	# Only RM4,000 - RM3,300 = RM700 may be added.
	assert with_full_c11a.chargeable_income_normal == d("17000.00")


def test_c11_epf_claim_below_the_remaining_sublimit_is_added_in_full():
	result = calculate_pcb(_c11_input(current_c11_epf=d(500)))
	assert result.chargeable_income_normal == d("17200.00")


def test_c11_life_claim_is_independent_of_compulsory_epf_and_capped_at_rm3000():
	# RM3,000 life insurance relief is added even though compulsory EPF already
	# consumes its own RM4,000 sublimit.
	result = calculate_pcb(_c11_input(current_c11_life=d(3000)))
	assert result.chargeable_income_normal == d("14700.00")

	over_claim = calculate_pcb(_c11_input(current_c11_life=d(5000)))
	assert over_claim.chargeable_income_normal == d("14700.00")


def test_c11_epf_claim_without_compulsory_epf_is_not_reduced():
	"""A payroll with no EPF (for example a non-contributing category) leaves the full RM4,000."""
	result = calculate_pcb(
		_c11_input(current_normal_epf=d(0), current_c11_epf=d(4000), current_c11_life=d(3000))
	)
	# P before C11 = 2,500 + 2,500 x 11 - 9,000 = 21,000; reliefs 4,000 + 3,000.
	assert result.chargeable_income_normal == d("14000.00")


def test_c11_prior_and_current_claims_share_one_sublimit():
	"""Claims made earlier in the year and this month draw on the same RM4,000 cap."""
	without_c11 = calculate_pcb(
		_c11_input(month=8, current_normal_gross=d(6000), current_normal_epf=d(660))
	)
	with_c11 = calculate_pcb(
		_c11_input(
			month=8,
			current_normal_gross=d(6000),
			current_normal_epf=d(660),
			prior_c11_epf=d(1000),
			current_c11_epf=d(1000),
		)
	)

	# P = 5,340 + (6,000 - 660) x 4 - 9,000 = 17,700 before C11. Annual EPF relief is
	# 660 + 660 x 4 = 3,300, leaving RM700 of the RM4,000 sublimit for 2,000 of claims.
	assert without_c11.chargeable_income_normal == d("17700.00")
	assert with_c11.chargeable_income_normal == d("17000.00")


def test_c11_epf_claim_without_compulsory_epf_is_not_reduced():
	"""A payroll with no EPF (for example a non-contributing category) leaves the full RM4,000."""
	result = calculate_pcb(
		_c11_input(current_normal_epf=d(0), current_c11_epf=d(4000), current_c11_life=d(3000))
	)
	# P before C11 = 2,500 + 2,500 x 11 - 9,000 = 21,000; reliefs 4,000 + 3,000.
	assert result.chargeable_income_normal == d("14000.00")


def test_c11_prior_and_current_claims_share_one_sublimit():
	"""Claims made earlier in the year and this month draw on the same RM4,000 cap."""
	without_c11 = calculate_pcb(
		_c11_input(month=8, current_normal_gross=d(6000), current_normal_epf=d(660))
	)
	with_c11 = calculate_pcb(
		_c11_input(
			month=8,
			current_normal_gross=d(6000),
			current_normal_epf=d(660),
			prior_c11_epf=d(1000),
			current_c11_epf=d(1000),
		)
	)

	# P = 5,340 + (6,000 - 660) x 4 - 9,000 = 17,700 before C11. Annual EPF relief is
	# 660 + 660 x 4 = 3,300, leaving RM700 of the RM4,000 sublimit for 2,000 of claims.
	assert without_c11.chargeable_income_normal == d("17700.00")
	assert with_c11.chargeable_income_normal == d("17000.00")


def test_zakat_offset_matches_official_additional_remuneration_worked_cases():
	"""HASiL 2026 specification, section E.5(ii) table, rows (a)-(e).

	(normal MTD after the RM10 floor, additional MTD, current zakat) -> additional payable
	"""
	from malaysia_workforce.statutory.calculators.pcb import _zakat_offset

	cases = [
		(d("0.00"), d("0.00"), d("5.00"), d("0.00")),
		(d("0.00"), d("25.00"), d("5.00"), d("20.00")),
		(d("15.00"), d("32.55"), d("20.00"), d("27.55")),
		(d("15.00"), d("127.30"), d("8.00"), d("127.30")),
		(d("120.00"), d("392.25"), d("100.00"), d("392.25")),
	]
	for normal_before, additional, zakat, expected in cases:
		_offset, payable = _zakat_offset(normal_before, additional, zakat)
		assert payable == expected, (normal_before, additional, zakat, payable)


def _c11_combination_input(**overrides):
	"""RM5,000 normal pay plus a RM2,000 bonus in February, after a previous employer.

	Previous employer EPF is RM1,100 and January EPF RM550, so the annual EPF relief is
	already at its RM4,000 cap before any C11A claim.
	"""
	base = dict(
		month=2,
		resident=True,
		category=1,
		current_normal_gross=d(5000),
		current_additional_gross=d(2000),
		current_normal_epf=d(550),
		current_additional_epf=d(220),
		prior_gross=d(15000),
		prior_epf_relief=d(1650),
		prior_mtd=d("189.20"),
		current_c11_epf=d(4000),
		current_c11_life=d(3000),
	)
	base.update(overrides)
	return PCBInput(**base)


def test_c11_epf_gives_no_relief_when_previous_employer_and_bonus_epf_fill_the_cap():
	with_c11a = calculate_pcb(_c11_combination_input())
	without_c11a = calculate_pcb(_c11_combination_input(current_c11_epf=d(0)))

	# P1 = (15,000 - 1,650) + (5,000 - 550) + (5,000 - 180) x 10 - 12,000 = 54,000.
	# P2 adds (2,000 - 220) = 1,780 -> 56,000. EPF relief is already RM4,000, so the
	# RM4,000 C11A claim adds nothing; only C11B's RM3,000 applies.
	assert with_c11a.chargeable_income_normal == d("54000.00")
	assert with_c11a.chargeable_income_with_additional == d("56000.00")
	assert with_c11a.projected_epf_with_additional == d("4000.00")
	assert with_c11a.payable == d("378.80")
	assert without_c11a.chargeable_income_with_additional == d("56000.00")
	assert without_c11a.payable == with_c11a.payable


def test_c11_epf_partial_relief_with_previous_employer_and_bonus_epf():
	"""Lower wages leave part of the RM4,000 EPF sublimit for C11A.

	K = 550 (previous employer) + 275 (normal) + 55 (bonus) + 275 x 10 = 3,630,
	so C11A is limited to 4,000 - 3,630 = 370.
	"""
	with_c11a = calculate_pcb(
		_c11_combination_input(
			current_normal_gross=d(2500),
			current_additional_gross=d(500),
			current_normal_epf=d(275),
			current_additional_epf=d(55),
			prior_gross=d(5000),
			prior_epf_relief=d(550),
			prior_mtd=d(0),
		)
	)
	without_c11a = calculate_pcb(
		_c11_combination_input(
			current_normal_gross=d(2500),
			current_additional_gross=d(500),
			current_normal_epf=d(275),
			current_additional_epf=d(55),
			prior_gross=d(5000),
			prior_epf_relief=d(550),
			prior_mtd=d(0),
			current_c11_epf=d(0),
		)
	)
	assert with_c11a.projected_epf_with_additional == d("3630.00")
	assert without_c11a.chargeable_income_with_additional == d("17370.00")
	assert with_c11a.chargeable_income_with_additional == d("17000.00")

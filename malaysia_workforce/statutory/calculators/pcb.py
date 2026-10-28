from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from malaysia_workforce.statutory.common import PCBInput, PCBResult, ZERO, decimal, money, round_up_5_sen, truncate

RULE_VERSION = "LHDN-MTD-2026-2026-01-01"
INDIVIDUAL_RELIEF = Decimal("9000")
SPOUSE_RELIEF = Decimal("4000")
DISABLED_INDIVIDUAL_RELIEF = Decimal("7000")
DISABLED_SPOUSE_RELIEF = Decimal("6000")
CHILD_UNIT_RELIEF = Decimal("2000")
# Income Tax Act s.49(1)/(1A): EPF contributions (compulsory or voluntary) are relieved up to
# RM4,000, life insurance/takaful and additional voluntary EPF up to RM3,000, total RM7,000.
EPF_RELIEF_LIMIT = Decimal("4000")
LIFE_INSURANCE_RELIEF_LIMIT = Decimal("3000")

# (lower exclusive, upper inclusive, M, R, B category 1/3, B category 2)
TAX_BANDS = (
	(Decimal("5000"), Decimal("20000"), Decimal("5000"), Decimal("0.01"), Decimal("-400"), Decimal("-800")),
	(Decimal("20000"), Decimal("35000"), Decimal("20000"), Decimal("0.03"), Decimal("-250"), Decimal("-650")),
	(Decimal("35000"), Decimal("50000"), Decimal("35000"), Decimal("0.06"), Decimal("600"), Decimal("600")),
	(Decimal("50000"), Decimal("70000"), Decimal("50000"), Decimal("0.11"), Decimal("1500"), Decimal("1500")),
	(Decimal("70000"), Decimal("100000"), Decimal("70000"), Decimal("0.19"), Decimal("3700"), Decimal("3700")),
	(Decimal("100000"), Decimal("400000"), Decimal("100000"), Decimal("0.25"), Decimal("9400"), Decimal("9400")),
	(Decimal("400000"), Decimal("600000"), Decimal("400000"), Decimal("0.26"), Decimal("84400"), Decimal("84400")),
	(Decimal("600000"), Decimal("2000000"), Decimal("600000"), Decimal("0.28"), Decimal("136400"), Decimal("136400")),
	(Decimal("2000000"), Decimal("999999999999"), Decimal("2000000"), Decimal("0.30"), Decimal("528400"), Decimal("528400")),
)


def _reliefs(args: PCBInput, epf_relief_counted: Decimal) -> Decimal:
	"""Annual reliefs, applying the C11 sublimits to what EPF has already relieved.

	C11A (voluntary EPF) is limited to RM4,000 *including* compulsory EPF, so only the
	amount left after the EPF relief already counted in P can be added. C11B (life
	insurance/takaful or additional voluntary EPF) is independent and limited to RM3,000.
	A lump C11 claim is never added on top of the automatic EPF relief.
	"""
	spouse = SPOUSE_RELIEF if args.category == 2 else ZERO
	c11_life = min(
		decimal(args.prior_c11_life) + decimal(args.current_c11_life), LIFE_INSURANCE_RELIEF_LIMIT
	)
	c11_epf = min(
		decimal(args.prior_c11_epf) + decimal(args.current_c11_epf),
		max(EPF_RELIEF_LIMIT - decimal(epf_relief_counted), ZERO),
	)
	return (
		INDIVIDUAL_RELIEF
		+ spouse
		+ (DISABLED_INDIVIDUAL_RELIEF if args.individual_disabled else ZERO)
		+ (DISABLED_SPOUSE_RELIEF if args.spouse_disabled and args.category == 2 else ZERO)
		+ CHILD_UNIT_RELIEF * decimal(args.child_units)
		+ decimal(args.prior_optional_reliefs)
		+ decimal(args.current_optional_reliefs)
		+ c11_life
		+ c11_epf
	)


def _band_tax(chargeable_income: Decimal, category: int, tax_regime: str) -> Decimal:
	p = max(truncate(chargeable_income), ZERO)
	regime = (tax_regime or "STANDARD").upper()
	if regime != "STANDARD":
		raise ValueError(
			f"PCB tax regime {regime} is not implemented with reviewed eligibility and effective-date rules"
		)
	if p <= Decimal("5000"):
		return ZERO
	for lower, upper, m, rate, b13, b2 in TAX_BANDS:
		if lower < p <= upper:
			base = b2 if category == 2 else b13
			return max(truncate((p - m) * rate + base), ZERO)
	raise ValueError(f"No PCB tax band for chargeable income {p}")


def _qualified_current_epf(prior: Decimal, current: Decimal, limit: Decimal) -> Decimal:
	return max(min(decimal(current), max(limit - decimal(prior), ZERO)), ZERO)


def leaver_breaks_annual_projection(relieving_date: date | None, slip_end: date) -> bool:
	"""True when a recorded relieving date invalidates _annual_projection's continued-employment
	assumption: it always projects estimated_future_normal_gross through 31 December regardless
	of which month is being calculated, so any relieving date earlier in the same tax year breaks it
	— not just one falling within or before the slip's own period.
	"""
	return bool(relieving_date and relieving_date < date(slip_end.year, 12, 31))


def _annual_projection(args: PCBInput, *, include_additional: bool) -> tuple[Decimal, Decimal]:
	n = 12 - int(args.month)
	limit = decimal(args.epf_relief_limit)
	prior_k = min(max(decimal(args.prior_epf_relief), ZERO), limit)
	k1 = _qualified_current_epf(prior_k, decimal(args.current_normal_epf), limit)
	kt = ZERO
	if include_additional:
		kt = _qualified_current_epf(prior_k + k1, decimal(args.current_additional_epf), limit)
	remaining = max(limit - prior_k - k1 - kt, ZERO)
	if n > 0:
		k2 = min(truncate(remaining / Decimal(n)), k1)
	else:
		k2 = ZERO
	future_gross = decimal(args.estimated_future_normal_gross) if args.estimated_future_normal_gross is not None else decimal(args.current_normal_gross)
	net_prior = decimal(args.prior_gross) - prior_k
	net_current = decimal(args.current_normal_gross) - k1
	net_future = (future_gross - k2) * Decimal(n)
	net_additional = decimal(args.current_additional_gross) - kt if include_additional else ZERO
	epf_relief = prior_k + k1 + kt + k2 * Decimal(n)
	p = net_prior + net_current + net_future + net_additional - _reliefs(args, epf_relief)
	return truncate(max(p, ZERO)), truncate(epf_relief)


def _zakat_offset(normal_before_zakat, additional_mtd, current_zakat) -> tuple[Decimal, Decimal]:
	"""Apply the current month's zakat exactly as HASiL's worked table does.

	Zakat is absorbed by the MTD actually payable for the month (the amount after the
	RM10 floor). Any remainder reduces the additional-remuneration MTD; it is not lost
	and not applied twice. Returns (offset applied to additional MTD, additional payable).

	HASiL 2026 specification, section E.5(ii): normal MTD 8 -> 0, zakat 5, additional
	25 -> 20; normal MTD 15, zakat 20, additional 32.55 -> 27.55.
	"""
	zakat = max(decimal(current_zakat), ZERO)
	absorbed = min(zakat, max(decimal(normal_before_zakat), ZERO))
	excess = max(zakat - absorbed, ZERO)
	offset = min(excess, max(decimal(additional_mtd), ZERO))
	return money(offset), money(max(decimal(additional_mtd) - offset, ZERO))


def _normal_mtd(args: PCBInput, chargeable: Decimal) -> tuple[Decimal, Decimal]:
	n_plus_one = Decimal(13 - int(args.month))
	annual_tax = _band_tax(chargeable, args.category, args.tax_regime)
	raw = truncate((annual_tax - decimal(args.prior_zakat) - decimal(args.prior_mtd)) / n_plus_one)
	before_zakat = ZERO if raw < Decimal("10") else round_up_5_sen(raw)
	after_zakat = round_up_5_sen(max(before_zakat - decimal(args.current_zakat), ZERO))
	return annual_tax, after_zakat


def calculate_pcb(args: PCBInput) -> PCBResult:
	if not 1 <= int(args.month) <= 12:
		raise ValueError("PCB month must be between 1 and 12")
	if args.category not in {1, 2, 3}:
		raise ValueError("PCB category must be 1, 2 or 3")
	if (args.tax_regime or "STANDARD").upper() != "STANDARD":
		raise ValueError(
			f"PCB tax regime {(args.tax_regime or '').upper()} is not implemented with reviewed eligibility and effective-date rules"
		)

	if not args.resident:
		taxable = max(
			decimal(args.current_normal_gross)
			+ decimal(args.current_additional_gross)
			- decimal(args.nonresident_exempt_remuneration),
			ZERO,
		)
		before = round_up_5_sen(truncate(taxable * Decimal("0.30")))
		payable = ZERO if before < Decimal("10") else round_up_5_sen(max(before - decimal(args.current_zakat), ZERO))
		return PCBResult(
			payable=payable,
			normal_mtd_before_zakat=before,
			normal_mtd_after_zakat=payable,
			additional_mtd=ZERO,
			chargeable_income_normal=taxable,
			chargeable_income_with_additional=taxable,
			annual_tax_normal=before,
			annual_tax_with_additional=before,
			projected_epf_normal=ZERO,
			projected_epf_with_additional=ZERO,
			category=args.category,
			rule_version=RULE_VERSION,
			explanation=("Non-resident MTD at 30% of current taxable remuneration",),
		)

	chargeable_normal, projected_epf_normal = _annual_projection(args, include_additional=False)
	annual_tax_normal, normal_after_zakat = _normal_mtd(args, chargeable_normal)
	raw_normal_before = truncate(
		(annual_tax_normal - decimal(args.prior_zakat) - decimal(args.prior_mtd)) / Decimal(13 - int(args.month))
	)
	normal_before_zakat = ZERO if raw_normal_before < Decimal("10") else round_up_5_sen(raw_normal_before)
	# Step 1[E] of the 2026 specification projects the year using Step [C], the monthly
	# MTD *before* the RM10 floor. Using the floored amount would make the additional
	# remuneration absorb the whole annual tax whenever normal MTD falls below RM10.
	normal_for_projection = round_up_5_sen(raw_normal_before) if raw_normal_before > ZERO else ZERO

	chargeable_with_additional, projected_epf_with_additional = _annual_projection(args, include_additional=True)
	annual_tax_with_additional = _band_tax(chargeable_with_additional, args.category, args.tax_regime)
	additional_mtd = ZERO
	if decimal(args.current_additional_gross) > ZERO:
		projected_normal_mtd_year = decimal(args.prior_mtd) + normal_for_projection * Decimal(13 - int(args.month))
		raw_additional = truncate(
			annual_tax_with_additional
			- projected_normal_mtd_year
			- decimal(args.prior_zakat)
		)
		additional_mtd = ZERO if raw_additional < Decimal("10") else round_up_5_sen(raw_additional)

	zakat_offset_additional, additional_payable = _zakat_offset(
		normal_before_zakat, additional_mtd, args.current_zakat
	)
	payable = round_up_5_sen(normal_after_zakat + additional_payable)
	explanation = [
		"LHDN computerized MTD formula for normal remuneration",
		"Additional remuneration formula applied when current additional remuneration is positive",
		"Intermediate calculations truncated to two decimals; final MTD rounded up to five sen",
	]
	if zakat_offset_additional:
		explanation.append(
			f"Zakat not absorbed by this month's MTD offset the additional remuneration MTD by {zakat_offset_additional}"
		)
	return PCBResult(
		payable=payable,
		normal_mtd_before_zakat=normal_before_zakat,
		normal_mtd_after_zakat=normal_after_zakat,
		additional_mtd=additional_mtd,
		zakat_offset_additional=zakat_offset_additional,
		chargeable_income_normal=chargeable_normal,
		chargeable_income_with_additional=chargeable_with_additional,
		annual_tax_normal=annual_tax_normal,
		annual_tax_with_additional=annual_tax_with_additional,
		projected_epf_normal=projected_epf_normal,
		projected_epf_with_additional=projected_epf_with_additional,
		category=args.category,
		rule_version=RULE_VERSION,
		explanation=tuple(explanation),
	)

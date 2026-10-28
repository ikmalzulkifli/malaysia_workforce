from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN
from functools import lru_cache
from pathlib import Path
from typing import Any

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
FIVE_SEN = Decimal("0.05")
DATA_DIR = Path(__file__).resolve().parent / "data"


def decimal(value: Any, default: str = "0") -> Decimal:
	"""Convert a value to a finite Decimal for statutory calculations."""
	try:
		result = Decimal(default) if value is None or value == "" else (value if isinstance(value, Decimal) else Decimal(str(value)))
	except (InvalidOperation, TypeError, ValueError) as exc:
		raise ValueError(f"Invalid decimal value: {value!r}") from exc
	if not result.is_finite():
		raise ValueError(f"Decimal value must be finite: {value!r}")
	return result


def truncate(value: Any, places: int = 2) -> Decimal:
	return decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_DOWN)


def money(value: Any) -> Decimal:
	return decimal(value).quantize(CENT)


def ceil_ringgit(value: Any) -> Decimal:
	return decimal(value).quantize(Decimal("1"), rounding=ROUND_CEILING).quantize(CENT)


def round_up_5_sen(value: Any) -> Decimal:
	amount = max(decimal(value), ZERO)
	units = (amount / FIVE_SEN).quantize(Decimal("1"), rounding=ROUND_CEILING)
	return (units * FIVE_SEN).quantize(CENT)


@lru_cache(maxsize=None)
def load_csv(filename: str) -> tuple[dict[str, str], ...]:
	with (DATA_DIR / filename).open(newline="", encoding="utf-8") as handle:
		return tuple(csv.DictReader(handle))


@dataclass(frozen=True)
class ContributionResult:
	scheme: str
	wage_base: Decimal
	employee: Decimal = ZERO
	employer: Decimal = ZERO
	extra_employee: Decimal = ZERO
	applicable: bool = True
	category: str = ""
	rule_version: str = ""
	explanation: tuple[str, ...] = field(default_factory=tuple)

	@property
	def total(self) -> Decimal:
		return money(self.employee + self.employer + self.extra_employee)

	def to_dict(self) -> dict[str, Any]:
		result = asdict(self)
		for key in ("wage_base", "employee", "employer", "extra_employee"):
			result[key] = str(result[key])
		result["total"] = str(self.total)
		return result


@dataclass(frozen=True)
class PCBInput:
	month: int
	resident: bool
	category: int
	current_normal_gross: Decimal
	current_additional_gross: Decimal = ZERO
	prior_gross: Decimal = ZERO
	prior_epf_relief: Decimal = ZERO
	current_normal_epf: Decimal = ZERO
	current_additional_epf: Decimal = ZERO
	# Optional (non-C11) reliefs already claimed before this month and in this month.
	prior_optional_reliefs: Decimal = ZERO
	current_optional_reliefs: Decimal = ZERO
	# C11 sublimits, kept apart because they interact with the automatic EPF relief.
	# C11A is voluntary EPF (RM4,000 including compulsory EPF); C11B is life insurance,
	# takaful or additional voluntary EPF (RM3,000).
	prior_c11_epf: Decimal = ZERO
	prior_c11_life: Decimal = ZERO
	current_c11_epf: Decimal = ZERO
	current_c11_life: Decimal = ZERO
	prior_zakat: Decimal = ZERO
	current_zakat: Decimal = ZERO
	prior_mtd: Decimal = ZERO
	child_units: Decimal = ZERO
	individual_disabled: bool = False
	spouse_disabled: bool = False
	estimated_future_normal_gross: Decimal | None = None
	epf_relief_limit: Decimal = Decimal("4000")
	tax_regime: str = "STANDARD"
	nonresident_exempt_remuneration: Decimal = ZERO


@dataclass(frozen=True)
class PCBResult:
	payable: Decimal
	normal_mtd_before_zakat: Decimal
	normal_mtd_after_zakat: Decimal
	additional_mtd: Decimal
	chargeable_income_normal: Decimal
	chargeable_income_with_additional: Decimal
	annual_tax_normal: Decimal
	annual_tax_with_additional: Decimal
	projected_epf_normal: Decimal
	projected_epf_with_additional: Decimal
	category: int
	rule_version: str = "LHDN-MTD-2026-2026-01-01"
	explanation: tuple[str, ...] = field(default_factory=tuple)

	def to_dict(self) -> dict[str, Any]:
		result = asdict(self)
		for key, value in tuple(result.items()):
			if isinstance(value, Decimal):
				result[key] = str(value)
		return result


def effective_warning(as_of: date, reviewed_through: date) -> str | None:
	if as_of > reviewed_through:
		return f"Rule data has not been reviewed after {reviewed_through.isoformat()}"
	return None

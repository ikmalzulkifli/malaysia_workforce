import json
from decimal import Decimal
from pathlib import Path

from malaysia_workforce.payroll.tax_validation import validate_tp1_rows

DATA = Path(__file__).resolve().parents[1] / "statutory" / "data" / "tp1_reliefs_2026.json"


def row(code: str, amount: str, month: int = 1) -> dict:
	return {
		"relief_code": code,
		"amount": Decimal(amount),
		"claim_month": month,
		"evidence_reference": "synthetic-receipt",
	}


def raises_value_error(rows, fragment: str) -> None:
	try:
		validate_tp1_rows(rows, tax_year=2026)
	except ValueError as exc:
		assert fragment.lower() in str(exc).lower(), str(exc)
	else:
		raise AssertionError(f"Expected ValueError containing {fragment!r}")


def test_catalogue_splits_c11_into_the_two_official_sublimits():
	reliefs = json.loads(DATA.read_text())["reliefs"]
	assert "C11" not in reliefs
	assert Decimal(reliefs["C11A"]["annual_limit"]) == Decimal("4000")
	assert Decimal(reliefs["C11B"]["annual_limit"]) == Decimal("3000")


def test_c11a_and_c11b_within_their_sublimits_are_accepted():
	cleaned = validate_tp1_rows([row("C11A", "4000"), row("C11B", "3000")], tax_year=2026)
	assert [item["relief_code"] for item in cleaned] == ["C11A", "C11B"]


def test_c11a_above_rm4000_is_rejected():
	raises_value_error([row("C11A", "4000.01")], "exceeds")


def test_c11b_above_rm3000_is_rejected():
	raises_value_error([row("C11B", "3000.01")], "exceeds")


def test_legacy_lump_sum_c11_must_be_itemised():
	raises_value_error([row("C11", "7000")], "split")


def test_c11_claims_still_require_evidence():
	rows = [row("C11B", "1000")]
	rows[0]["evidence_reference"] = ""
	raises_value_error(rows, "evidence")

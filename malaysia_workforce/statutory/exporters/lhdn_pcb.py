from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from malaysia_workforce.statutory.exporters.common import assert_length, cents, digits, fixed_text

HEADER_LENGTH = 57
DETAIL_LENGTH = 136


@dataclass(frozen=True)
class LHDNPCBRecord:
	tin: str
	name: str
	old_ic: str = ""
	new_ic: str = ""
	passport: str = ""
	country_code: str = ""
	mtd_amount: Decimal = Decimal("0")
	cp38_amount: Decimal = Decimal("0")
	employee_number: str = ""


def _numeric(value: str, length: int, label: str, *, required: bool = True) -> str:
	clean = digits(value)
	if required and not clean:
		raise ValueError(f"{label} is required")
	if len(clean) > length:
		raise ValueError(f"{label} exceeds {length} numeric digits")
	return clean.zfill(length)


def _text_max(value: str, length: int, label: str) -> str:
	text = "" if value is None else str(value)
	try:
		text.encode("ascii")
	except UnicodeEncodeError as exc:
		raise ValueError(f"{label} contains non-ASCII characters; provide the authority-approved ASCII spelling") from exc
	if any(character in text for character in ("\r", "\n", "\x00")):
		raise ValueError(f"{label} contains an unsupported control character")
	if len(text) > length:
		raise ValueError(f"{label} exceeds {length} ASCII characters")
	return text


def render_header(
	*, hq_number: str, employer_number: str, year: int, month: int, records: Iterable[LHDNPCBRecord]
) -> str:
	items = tuple(records)
	if not 1 <= int(month) <= 12:
		raise ValueError("LHDN month must be between 1 and 12")
	if int(year) < 2000 or int(year) > 9999:
		raise ValueError("LHDN year must contain four digits")
	# Exhibit 4 fields 7 and 9 are separate counts: "Total MTD Records" tallies employees
	# subject to MTD and "Total CP38 Records" tallies employees subject to CP38 (their
	# worked example shows 6 MTD records and 2 CP38 records in the same file). A single
	# count for both under-reports one field whenever the two differ.
	#
	# A detail line is still written for every record, including zero/zero employees.
	# Whether such a line should be omitted is not settled by Exhibit 4/5, so it is left
	# in place rather than dropped on assumption; it simply counts in neither field.
	mtd_records = sum(1 for item in items if Decimal(str(item.mtd_amount or 0)) > 0)
	cp38_records = sum(1 for item in items if Decimal(str(item.cp38_amount or 0)) > 0)
	record = "".join(
		(
			"H",
			_numeric(hq_number, 10, "LHDN HQ employer number"),
			_numeric(employer_number, 10, "LHDN employer number"),
			str(int(year)).zfill(4),
			str(int(month)).zfill(2),
			cents(sum((item.mtd_amount for item in items), Decimal("0")), 10),
			str(mtd_records).zfill(5),
			cents(sum((item.cp38_amount for item in items), Decimal("0")), 10),
			str(cp38_records).zfill(5),
		)
	)
	return assert_length(record, HEADER_LENGTH, "LHDN PCB header")


def render_detail(item: LHDNPCBRecord) -> str:
	name = _text_max(item.name, 60, "Employee name")
	if not name.encode("ascii", errors="ignore").decode("ascii").strip():
		raise ValueError("LHDN employee name is required")
	if item.mtd_amount < 0 or item.cp38_amount < 0:
		raise ValueError("LHDN MTD and CP38 amounts cannot be negative")
	if item.passport and len(item.country_code or "") != 2:
		raise ValueError("LHDN country code must contain two characters when a passport is used")
	if not (digits(item.old_ic) or digits(item.new_ic) or item.passport):
		raise ValueError("LHDN record requires an old IC, new IC or passport")
	record = "".join(
		(
			"D",
			_numeric(item.tin, 11, "LHDN TIN"),
			fixed_text(name, 60, uppercase=True),
			fixed_text(_text_max(item.old_ic, 12, "Old IC"), 12, uppercase=True),
			fixed_text(_text_max(digits(item.new_ic), 12, "New IC"), 12),
			fixed_text(_text_max(item.passport, 12, "Passport"), 12, uppercase=True),
			fixed_text(_text_max(item.country_code, 2, "Country code"), 2, uppercase=True),
			cents(item.mtd_amount, 8),
			cents(item.cp38_amount, 8),
			fixed_text(_text_max(item.employee_number, 10, "Employee number"), 10, uppercase=True),
		)
	)
	return assert_length(record, DETAIL_LENGTH, "LHDN PCB detail")


def generate_lhdn_pcb_file(
	*, hq_number: str, employer_number: str, year: int, month: int, records: Iterable[LHDNPCBRecord]
) -> bytes:
	items = tuple(records)
	if not items:
		raise ValueError("LHDN PCB file requires at least one employee record")
	lines = [
		render_header(
			hq_number=hq_number,
			employer_number=employer_number,
			year=year,
			month=month,
			records=items,
		)
	]
	lines.extend(render_detail(item) for item in items)
	return ("\r\n".join(lines) + "\r\n").encode("ascii")

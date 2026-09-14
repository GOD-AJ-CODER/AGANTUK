"""
core/mrz.py — ICAO 9303 Machine Readable Zone (MRZ) parser and Modulo-10 validator.

Rules Reference:
  - Rule 4.1: MRZ Structure & Character Whitelist
      * TD1: 3 lines x 30 characters
      * TD2: 2 lines x 36 characters
      * TD3: 2 lines x 44 characters (Passports)
      * Allowed characters: ^[A-Z0-9<]+$
      * Violations trigger ERR_MATH_MALFORMED_MRZ_STRUCTURE or ERR_MATH_INVALID_MRZ_CHARACTERS.
  - Rule 4.3: ICAO 9303 Weighted Modulo-10 Checksum:
      * Character weights: [7, 3, 1] repeating
      * Character values: 0-9 -> 0-9, A-Z -> 10-35, < -> 0
      * Checksums validated for:
          - Document Number (ERR_MATH_MOD10_DOC_NUM_FAILED)
          - Date of Birth (ERR_MATH_MOD10_DOB_FAILED)
          - Expiry Date (ERR_MATH_MOD10_EXPIRY_FAILED)
          - Composite Master (ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED)
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from app.schemas.verification import FailureCode

# Character mapping per ICAO 9303 Part 3
CHAR_WEIGHTS = [7, 3, 1]

MRZ_CHAR_MAP = {
    "<": 0,
    **{str(d): d for d in range(10)},
    **{chr(ord("A") + i): 10 + i for i in range(26)},
}

MRZ_VALID_CHAR_PATTERN = re.compile(r"^[A-Z0-9<]+$")


@dataclass
class CheckDigitResult:
    field_name: str
    data_string: str
    expected_digit: str
    calculated_digit: str
    is_valid: bool


@dataclass
class ParsedMRZ:
    raw_lines: list[str]
    format_type: str  # "TD1", "TD2", "TD3", or "UNKNOWN"
    document_type: str
    issuing_country: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    date_of_birth: str  # YYMMDD
    sex: str
    expiry_date: str  # YYMMDD
    optional_data: str
    check_digits: dict[str, CheckDigitResult] = field(default_factory=dict)
    failure_codes: list[FailureCode] = field(default_factory=list)
    is_valid: bool = True


# ─── Modulo-10 Engine ─────────────────────────────────────────────────────────


def calculate_mod10_digit(data: str) -> str:
    """
    Calculate ICAO 9303 Modulo-10 check digit for an alphanumeric string.

    Weights: [7, 3, 1] repeating.
    Returns single digit string "0"-"9".
    """
    total = 0
    for i, char in enumerate(data.upper()):
        val = MRZ_CHAR_MAP.get(char, 0)
        weight = CHAR_WEIGHTS[i % 3]
        total += val * weight
    return str(total % 10)


def verify_check_digit(field_name: str, data: str, expected_digit: str) -> CheckDigitResult:
    """Validate check digit against ICAO 9303 Modulo-10 checksum."""
    calc_digit = calculate_mod10_digit(data)
    is_valid = calc_digit == expected_digit
    return CheckDigitResult(
        field_name=field_name,
        data_string=data,
        expected_digit=expected_digit,
        calculated_digit=calc_digit,
        is_valid=is_valid,
    )


# ─── Name Parsing Helper ──────────────────────────────────────────────────────


def parse_mrz_name(raw_name: str) -> tuple[str, str]:
    """
    Parse MRZ name field formatted as SURNAME<<GIVEN<NAMES<<<<<.

    Returns:
        (surname, given_names)
    """
    cleaned = raw_name.rstrip("<")
    parts = cleaned.split("<<", 1)
    surname = parts[0].replace("<", " ").strip()
    given_names = parts[1].replace("<", " ").strip() if len(parts) > 1 else ""
    return surname, given_names


# ─── Format Parsers ───────────────────────────────────────────────────────────


def parse_td3(lines: list[str]) -> ParsedMRZ:
    """
    Parse ICAO 9303 TD3 (Passport: 2 lines x 44 characters).
    """
    line1, line2 = lines[0], lines[1]
    failures: list[FailureCode] = []

    # Line 1
    doc_type = line1[0:2].replace("<", "").strip()
    issuing_country = line1[2:5].replace("<", "").strip()
    surname, given_names = parse_mrz_name(line1[5:44])

    # Line 2
    doc_num_raw = line2[0:9]
    doc_num = doc_num_raw.replace("<", "").strip()
    doc_num_cd = line2[9:10]

    nationality = line2[10:13].replace("<", "").strip()
    dob = line2[13:19]
    dob_cd = line2[19:20]

    sex = line2[20:21].replace("<", "X")
    expiry = line2[21:27]
    expiry_cd = line2[27:28]

    optional_data = line2[28:42].replace("<", "").strip()
    optional_cd = line2[42:43]
    master_composite_cd = line2[43:44]

    # Validate Check Digits (Rule 4.3)
    cd_results: dict[str, CheckDigitResult] = {}

    # 1. Doc Number
    r_doc = verify_check_digit("document_number", doc_num_raw, doc_num_cd)
    cd_results["document_number"] = r_doc
    if not r_doc.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED)

    # 2. Date of Birth
    r_dob = verify_check_digit("date_of_birth", dob, dob_cd)
    cd_results["date_of_birth"] = r_dob
    if not r_dob.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_DOB_FAILED)

    # 3. Expiry Date
    r_exp = verify_check_digit("expiry_date", expiry, expiry_cd)
    cd_results["expiry_date"] = r_exp
    if not r_exp.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_EXPIRY_FAILED)

    # 4. Master Composite Check Digit
    # ICAO Doc 9303 Part 4 (TD3):
    # Composite string = doc_num(9) + doc_cd(1) + dob(6) + dob_cd(1) + expiry(6) + exp_cd(1) + optional(14) + opt_cd(1)
    # i.e., line2[0:10] + line2[13:20] + line2[21:43]
    composite_data = line2[0:10] + line2[13:20] + line2[21:43]
    r_master = verify_check_digit("composite", composite_data, master_composite_cd)
    cd_results["composite"] = r_master
    if not r_master.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED)

    is_valid = len(failures) == 0

    return ParsedMRZ(
        raw_lines=lines,
        format_type="TD3",
        document_type=doc_type or "PASSPORT",
        issuing_country=issuing_country,
        surname=surname,
        given_names=given_names,
        document_number=doc_num,
        nationality=nationality,
        date_of_birth=dob,
        sex=sex,
        expiry_date=expiry,
        optional_data=optional_data,
        check_digits=cd_results,
        failure_codes=failures,
        is_valid=is_valid,
    )


def parse_td1(lines: list[str]) -> ParsedMRZ:
    """
    Parse ICAO 9303 TD1 (ID cards: 3 lines x 30 characters).
    """
    line1, line2, line3 = lines[0], lines[1], lines[2]
    failures: list[FailureCode] = []

    # Line 1
    doc_type = line1[0:2].replace("<", "").strip()
    issuing_country = line1[2:5].replace("<", "").strip()
    doc_num_raw = line1[5:14]
    doc_num = doc_num_raw.replace("<", "").strip()
    doc_num_cd = line1[14:15]
    optional_1 = line1[15:30]

    # Line 2
    dob = line2[0:6]
    dob_cd = line2[6:7]
    sex = line2[7:8].replace("<", "X")
    expiry = line2[8:14]
    expiry_cd = line2[14:15]
    nationality = line2[15:18].replace("<", "").strip()
    optional_2 = line2[18:29]
    composite_cd = line2[29:30]

    # Line 3
    surname, given_names = parse_mrz_name(line3[0:30])

    # Check Digits
    cd_results: dict[str, CheckDigitResult] = {}

    r_doc = verify_check_digit("document_number", doc_num_raw, doc_num_cd)
    cd_results["document_number"] = r_doc
    if not r_doc.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED)

    r_dob = verify_check_digit("date_of_birth", dob, dob_cd)
    cd_results["date_of_birth"] = r_dob
    if not r_dob.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_DOB_FAILED)

    r_exp = verify_check_digit("expiry_date", expiry, expiry_cd)
    cd_results["expiry_date"] = r_exp
    if not r_exp.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_EXPIRY_FAILED)

    # TD1 Composite = line1[5:30] + line2[0:7] + line2[8:15] + line2[18:29]
    composite_data = line1[5:30] + line2[0:7] + line2[8:15] + line2[18:29]
    r_comp = verify_check_digit("composite", composite_data, composite_cd)
    cd_results["composite"] = r_comp
    if not r_comp.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED)

    is_valid = len(failures) == 0

    return ParsedMRZ(
        raw_lines=lines,
        format_type="TD1",
        document_type=doc_type or "NATIONAL_ID",
        issuing_country=issuing_country,
        surname=surname,
        given_names=given_names,
        document_number=doc_num,
        nationality=nationality,
        date_of_birth=dob,
        sex=sex,
        expiry_date=expiry,
        optional_data=(optional_1 + optional_2).replace("<", "").strip(),
        check_digits=cd_results,
        failure_codes=failures,
        is_valid=is_valid,
    )


def parse_td2(lines: list[str]) -> ParsedMRZ:
    """
    Parse ICAO 9303 TD2 (ID/Visa: 2 lines x 36 characters).
    """
    line1, line2 = lines[0], lines[1]
    failures: list[FailureCode] = []

    doc_type = line1[0:2].replace("<", "").strip()
    issuing_country = line1[2:5].replace("<", "").strip()
    surname, given_names = parse_mrz_name(line1[5:36])

    doc_num_raw = line2[0:9]
    doc_num = doc_num_raw.replace("<", "").strip()
    doc_num_cd = line2[9:10]
    nationality = line2[10:13].replace("<", "").strip()
    dob = line2[13:19]
    dob_cd = line2[19:20]
    sex = line2[20:21].replace("<", "X")
    expiry = line2[21:27]
    expiry_cd = line2[27:28]
    optional = line2[28:35]
    composite_cd = line2[35:36]

    cd_results: dict[str, CheckDigitResult] = {}

    r_doc = verify_check_digit("document_number", doc_num_raw, doc_num_cd)
    cd_results["document_number"] = r_doc
    if not r_doc.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_DOC_NUM_FAILED)

    r_dob = verify_check_digit("date_of_birth", dob, dob_cd)
    cd_results["date_of_birth"] = r_dob
    if not r_dob.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_DOB_FAILED)

    r_exp = verify_check_digit("expiry_date", expiry, expiry_cd)
    cd_results["expiry_date"] = r_exp
    if not r_exp.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_EXPIRY_FAILED)

    composite_data = line2[0:10] + line2[13:20] + line2[21:35]
    r_comp = verify_check_digit("composite", composite_data, composite_cd)
    cd_results["composite"] = r_comp
    if not r_comp.is_valid:
        failures.append(FailureCode.ERR_MATH_MOD10_MASTER_CHECKSUM_FAILED)

    is_valid = len(failures) == 0

    return ParsedMRZ(
        raw_lines=lines,
        format_type="TD2",
        document_type=doc_type or "VISA",
        issuing_country=issuing_country,
        surname=surname,
        given_names=given_names,
        document_number=doc_num,
        nationality=nationality,
        date_of_birth=dob,
        sex=sex,
        expiry_date=expiry,
        optional_data=optional.replace("<", "").strip(),
        check_digits=cd_results,
        failure_codes=failures,
        is_valid=is_valid,
    )


# ─── Master MRZ Parsing Entrypoint ───────────────────────────────────────────


def parse_mrz(raw_lines: list[str]) -> ParsedMRZ:
    """
    Parse MRZ lines, validating structure, character whitelist, and Modulo-10 checksums.

    Rules 4.1 & 4.3:
      - Validates line count and lengths (TD1: 3x30, TD2: 2x36, TD3: 2x44).
      - Enforces character whitelist ^[A-Z0-9<]+$.
      - Computes and validates Modulo-10 check digits.
    """
    # Clean whitespace and force uppercase
    cleaned_lines = [line.strip().upper() for line in raw_lines if line.strip()]

    # Validate structure (Rule 4.1)
    num_lines = len(cleaned_lines)
    detected_format = "UNKNOWN"

    if num_lines == 2:
        l1_len, l2_len = len(cleaned_lines[0]), len(cleaned_lines[1])
        if l1_len == 44 and l2_len == 44:
            detected_format = "TD3"
        elif l1_len == 36 and l2_len == 36:
            detected_format = "TD2"
    elif num_lines == 3:
        if all(len(line) == 30 for line in cleaned_lines):
            detected_format = "TD1"

    failures: list[FailureCode] = []

    # Check character whitelist on all lines (Rule 4.1)
    for line in cleaned_lines:
        if not MRZ_VALID_CHAR_PATTERN.match(line):
            failures.append(FailureCode.ERR_MATH_INVALID_MRZ_CHARACTERS)
            break

    if detected_format == "UNKNOWN":
        failures.append(FailureCode.ERR_MATH_MALFORMED_MRZ_STRUCTURE)
        return ParsedMRZ(
            raw_lines=cleaned_lines,
            format_type="UNKNOWN",
            document_type="UNKNOWN",
            issuing_country="",
            surname="",
            given_names="",
            document_number="",
            nationality="",
            date_of_birth="",
            sex="",
            expiry_date="",
            optional_data="",
            failure_codes=failures,
            is_valid=False,
        )

    # Delegate to specific format parser
    if detected_format == "TD3":
        result = parse_td3(cleaned_lines)
    elif detected_format == "TD1":
        result = parse_td1(cleaned_lines)
    elif detected_format == "TD2":
        result = parse_td2(cleaned_lines)
    else:
        result = ParsedMRZ(
            raw_lines=cleaned_lines,
            format_type="UNKNOWN",
            document_type="UNKNOWN",
            issuing_country="",
            surname="",
            given_names="",
            document_number="",
            nationality="",
            date_of_birth="",
            sex="",
            expiry_date="",
            optional_data="",
            failure_codes=[FailureCode.ERR_MATH_MALFORMED_MRZ_STRUCTURE],
            is_valid=False,
        )

    # Append any pre-parsing failures (e.g. invalid chars)
    for f in failures:
        if f not in result.failure_codes:
            result.failure_codes.append(f)
            result.is_valid = False

    return result

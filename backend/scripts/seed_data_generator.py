"""
Seed Dataset Generator for BimaSense AI (Milestone 1).
Generates realistic, multi-page, table-rich Indian Health Insurance Policy PDFs,
the IRDAI Master Circular on Health Insurance (2024) PDF, the IRDAI Annexure-I
Non-Payable Consumables PDF, and the 30-question Ragas evaluation benchmark JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
RAW_POLICIES_DIR = BACKEND_DIR / "data" / "raw_policies"
IRDAI_CIRCULARS_DIR = BACKEND_DIR / "data" / "irdai_circulars"
EVAL_DATASET_PATH = BACKEND_DIR / "data" / "eval_dataset.json"


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle(
            "DocTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            spaceAfter=10,
            textColor=colors.HexColor("#0F172A"),
        ),
        "H1": ParagraphStyle(
            "SectionH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor("#1E3A8A"),
        ),
        "H2": ParagraphStyle(
            "SectionH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            spaceBefore=8,
            spaceAfter=4,
            textColor=colors.HexColor("#1E293B"),
        ),
        "Body": ParagraphStyle(
            "BodyTextCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            spaceAfter=6,
        ),
    }


def _make_table(rows: list[list[str]], col_widths: list[float] | None = None) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _render_multipage_pdf(output_path: Path, doc_title: str, pages_data: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=doc_title,
    )
    story: list[Any] = []
    for idx, page in enumerate(pages_data):
        if idx == 0:
            story.append(Paragraph(doc_title, styles["Title"]))
        story.append(Paragraph(page["h1"], styles["H1"]))
        for section in page.get("sections", []):
            if section.get("h2"):
                story.append(Paragraph(section["h2"], styles["H2"]))
            for p_text in section.get("paragraphs", []):
                story.append(Paragraph(p_text, styles["Body"]))
            if section.get("table"):
                story.append(Spacer(1, 4))
                story.append(_make_table(section["table"], section.get("col_widths")))
                story.append(Spacer(1, 8))
        if idx < len(pages_data) - 1:
            story.append(PageBreak())
    doc.build(story)


def generate_policy_pdfs() -> list[Path]:
    """Generates 3 multi-page Indian health insurance policy wordings."""
    generated: list[Path] = []

    # 1. HDFC ERGO Optima Secure
    hdfc_path = RAW_POLICIES_DIR / "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf"
    hdfc_pages = [
        {
            "h1": "# Section 1: Inclusions, 4X Coverage & Room Rent Rules",
            "sections": [
                {
                    "h2": "## 1.1 Base Coverage, Secure Benefit & Plus Benefit",
                    "paragraphs": [
                        "Insurer: HDFC ERGO General Insurance Company Ltd. | Plan Name: Optima Secure | UIN: HDFHLIP24092V032324.",
                        "Clause 1.1.1 (Secure Benefit): Doubles the Base Sum Insured instantly from Day 1 of policy inception at no additional cost. A Rs. 10 Lakh Base Sum Insured immediately provides Rs. 20 Lakh coverage.",
                        "Clause 1.1.2 (Plus Benefit): Increases Base Sum Insured by 50% after Year 1 and up to 100% after Year 2 unconditionally, irrespective of any claims made.",
                        "Clause 1.2 (Room Rent & ICU Limit): There is NO Room Rent capping and NO ICU daily sub-limit under HDFC ERGO Optima Secure for any Sum Insured of Rs. 5 Lakhs and above. Insured members can choose any room category (including Single Private A/C or Deluxe Room) without attracting Proportionate Deduction under Clause 3.4.",
                    ],
                    "table": [
                        ["Benefit Feature", "Base SI: 5L", "Base SI: 10L", "Base SI: 20L"],
                        ["Room Rent Limit", "At Actuals (Any Room)", "At Actuals (Any Room)", "At Actuals (Any Room)"],
                        ["ICU Charges", "At Actuals (No Cap)", "At Actuals (No Cap)", "At Actuals (No Cap)"],
                        ["Secure Benefit (Day 1)", "+100% Base SI (5L)", "+100% Base SI (10L)", "+100% Base SI (20L)"],
                        ["Plus Benefit (After 2 Yrs)", "+100% Base SI (5L)", "+100% Base SI (10L)", "+100% Base SI (20L)"],
                        ["Automatic Restore Benefit", "100% Base SI (5L)", "100% Base SI (10L)", "100% Base SI (20L)"],
                        ["Protect Benefit (Consumables)", "Included (68 Items)", "Included (68 Items)", "Included (68 Items)"],
                    ],
                },
                {
                    "h2": "## 1.3 Protect Benefit (In-Built Non-Medical Consumables Cover)",
                    "paragraphs": [
                        "Clause 1.3.1: Protect Benefit is an in-built feature in Optima Secure that pays 100% for all 68 IRDAI Annexure-I Non-Payable Consumable items (such as surgical gloves, nebulization kit, oxygen mask, syringes, and gowns) when billed as part of an admissible inpatient hospitalization.",
                    ],
                },
            ],
        },
        {
            "h1": "# Section 2: Waiting Periods & Pre-Existing Diseases (PED)",
            "sections": [
                {
                    "h2": "## 2.1 Standard Waiting Periods Schedule",
                    "paragraphs": [
                        "Clause 2.1.1 (Initial 30-Day Waiting Period - Code Excl03): Expenses related to the treatment of any illness within 30 days from the first policy commencement date shall be excluded except claims arising directly due to an Accident.",
                        "Clause 2.1.2 (Specific Disease Waiting Period - Code Excl02): A 24-month continuous coverage waiting period applies to specified illnesses and surgical procedures including Cataract, Benign Prostatic Hypertrophy, Hernia, Hydrocele, Hysterectomy, Knee/Joint Replacement (non-accidental), Kidney Stones, and Gallbladder Stones.",
                        "Clause 2.1.3 (Pre-Existing Diseases - Code Excl01): Expenses related to the treatment of a Pre-Existing Disease (PED) such as Diabetes Mellitus, Hypertension, Hypothyroidism, or Asthma and its direct complications shall be excluded until the expiry of 36 months of continuous coverage after the date of inception of the first policy.",
                        "Clause 2.1.4 (Maternity Coverage Exclusion): Optima Secure does NOT cover Maternity or Childbirth expenses under the base policy (except ectopic pregnancy which is covered under inpatient surgical treatment).",
                    ],
                    "table": [
                        ["Waiting Period Type", "IRDAI Code", "Duration", "Key Covered / Excluded Conditions"],
                        ["Accidental Hospitalization", "N/A", "0 Days (Day 1)", "Immediate cashless & reimbursement cover"],
                        ["Initial Illness Waiting", "Excl03", "30 Days", "All non-accidental illnesses"],
                        ["Specific Listed Illnesses", "Excl02", "24 Months", "Cataract, Hernia, Joint Replacement, Renal Stones"],
                        ["Pre-Existing Diseases (PED)", "Excl01", "36 Months", "Diabetes, Hypertension, pre-declared chronic conditions"],
                        ["Maternity Benefit", "Excl18", "Not Covered", "Normal or C-section delivery excluded in base plan"],
                    ],
                }
            ],
        },
        {
            "h1": "# Section 3: Exclusions, Deductibles & Claim Settlement Procedure",
            "sections": [
                {
                    "h2": "## 3.1 Aggregate Deductible Waiver & Co-Payment",
                    "paragraphs": [
                        "Clause 3.1.1 (Mandatory Co-Payment): Zero mandatory age-based co-payment across all entry ages under HDFC ERGO Optima Secure.",
                        "Clause 3.1.2 (Optional Aggregate Deductible): Policyholders may voluntarily choose an Aggregate Deductible of Rs. 25,000, Rs. 50,000, or Rs. 1,00,000 per policy year in exchange for an upfront premium discount of 25% to 50%.",
                    ],
                },
                {
                    "h2": "## 3.2 Claim Notification & Cashless Turnaround",
                    "paragraphs": [
                        "Clause 3.2.1: For planned hospitalization, cashless pre-authorization must be requested at least 48 hours prior to admission. For emergency hospitalization, notification must be given within 24 hours of admission.",
                        "Clause 3.2.2: In accordance with IRDAI Master Circular 2024, cashless pre-authorization requests are processed within 1 hour of receipt, and final discharge authorization is granted within 3 hours of receiving the final hospital bill.",
                    ],
                },
            ],
        },
    ]
    _render_multipage_pdf(hdfc_path, "HDFC ERGO Optima Secure — Policy Wording", hdfc_pages)
    generated.append(hdfc_path)

    # 2. Star Health Comprehensive Insurance Policy
    star_path = RAW_POLICIES_DIR / "Star_Health_Comprehensive_Policy_Wording.pdf"
    star_pages = [
        {
            "h1": "# Section 1: Inclusions, Room Rent Cap & Proportionate Deduction",
            "sections": [
                {
                    "h2": "## 1.1 Room Rent Eligibility & Proportionate Deduction Clause",
                    "paragraphs": [
                        "Insurer: Star Health and Allied Insurance Co. Ltd. | Plan Name: Star Comprehensive | UIN: SHAHLIP22028V072122.",
                        "Clause 1.1.1 (Room Rent Limit): Room, boarding, and nursing expenses as provided by the Hospital are covered up to a Single Private A/C Room. Suite Room or Deluxe Room above Single Private A/C is NOT eligible.",
                        "Clause 1.1.2 (Proportionate Deduction Rule): If the Insured Person occupies a room category higher than the eligible Single Private A/C Room (or exceeds the numeric room rent cap), all Associated Medical Expenses (Surgeon Fees, Anesthetist Fees, OT Charges, Doctor Consultation, and Diagnostics) shall be reduced in the exact proportion of Eligible Room Rent to Actual Room Rent chosen.",
                        "Clause 1.1.3 (Exceptions to Proportionate Deduction): Proportionate deduction shall NOT be applied to the cost of Pharmacy/Medicines, Implants/Stents, Diagnostics (if tariff is uniform), or ICU charges.",
                    ],
                    "table": [
                        ["Benefit Parameter", "Sum Insured: 5L - 7.5L", "Sum Insured: 10L - 25L", "Sum Insured: 50L - 1Cr"],
                        ["Eligible Room Category", "Single Private A/C Room", "Single Private A/C Room", "Single Private A/C Room"],
                        ["ICU Charges", "At Actuals", "At Actuals", "At Actuals"],
                        ["Proportionate Deduction", "Applies if higher room chosen", "Applies if higher room chosen", "Applies if higher room chosen"],
                        ["Cataract Sub-Limit", "No Sub-Limit (Up to SI)", "No Sub-Limit (Up to SI)", "No Sub-Limit (Up to SI)"],
                        ["Automatic Restoration", "100% Once per Year", "100% Once per Year", "100% Once per Year"],
                    ],
                }
            ],
        },
        {
            "h1": "# Section 2: Waiting Periods, Maternity & Newborn Cover",
            "sections": [
                {
                    "h2": "## 2.1 Maternity, Newborn & PED Waiting Periods",
                    "paragraphs": [
                        "Clause 2.1.1 (Maternity Benefit): Covered after a waiting period of 24 months of continuous coverage under Star Comprehensive (provided both Self and Spouse are insured under a Floater policy). Normal Delivery is capped at Rs. 30,000 to Rs. 50,000 and Caesarean Section is capped at Rs. 40,000 to Rs. 1,00,000 depending on Sum Insured.",
                        "Clause 2.1.2 (Newborn Baby Cover): Covered from Day 1 of birth up to 10% of Sum Insured (maximum Rs. 1,00,000) when the mother's maternity claim is admissible.",
                        "Clause 2.1.3 (Pre-Existing Disease Waiting Period - Excl01): 36 months of continuous coverage for all declared Pre-Existing Diseases. Optional Buy-Back PED rider reduces the PED waiting period from 36 months to 12 months upon payment of additional premium.",
                        "Clause 2.1.4 (Specific Disease Waiting Period - Excl02): 24 months for Cataract, Hernia, Joint Replacement, Sinusitis, and Female Reproductive organ surgeries.",
                    ],
                    "table": [
                        ["Coverage / Waiting Clause", "Waiting Period", "Sub-Limit (SI 10L)", "Sub-Limit (SI 25L+)"],
                        ["Initial Illness Waiting", "30 Days", "Up to Sum Insured", "Up to Sum Insured"],
                        ["Specific Diseases (Excl02)", "24 Months", "Up to Sum Insured", "Up to Sum Insured"],
                        ["Pre-Existing Diseases (PED)", "36 Months (12M with Rider)", "Up to Sum Insured", "Up to Sum Insured"],
                        ["Maternity - Normal Delivery", "24 Months", "Rs. 30,000", "Rs. 50,000"],
                        ["Maternity - Caesarean (C-Sec)", "24 Months", "Rs. 50,000", "Rs. 1,00,000"],
                    ],
                }
            ],
        },
        {
            "h1": "# Section 3: Co-Payment, Consumables & Claim Procedure",
            "sections": [
                {
                    "h2": "## 3.1 Senior Citizen Co-Payment & Non-Payable Consumables",
                    "paragraphs": [
                        "Clause 3.1.1 (Mandatory Co-Payment): A mandatory 10% co-payment applies on each and every admissible claim for insured persons whose age at initial entry into the policy is 61 years or above. Zero co-payment for entry below age 60.",
                        "Clause 3.1.2 (Non-Payable Consumables): IRDAI Annexure-I 68 Non-Payable items are excluded under the base Star Comprehensive policy unless the optional Star Extra Protect Rider is purchased.",
                        "Clause 3.1.3 (No-Claim Bonus): Cumulative Bonus of 50% of Base Sum Insured for every claim-free year for SI up to 7.5L, and 100% after 1 claim-free year for SI of 10L and above (maximum accumulation 100% of Base SI).",
                    ],
                }
            ],
        },
    ]
    _render_multipage_pdf(star_path, "Star Health Comprehensive — Policy Wording", star_pages)
    generated.append(star_path)

    # 3. Niva Bupa ReAssure 2.0
    niva_path = RAW_POLICIES_DIR / "Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf"
    niva_pages = [
        {
            "h1": "# Section 1: ReAssure Forever Restoration, Booster+ & Room Rent",
            "sections": [
                {
                    "h2": "## 1.1 Unlimited Restoration & Room Rent Eligibility",
                    "paragraphs": [
                        "Insurer: Niva Bupa Health Insurance Co. Ltd. | Plan Name: ReAssure 2.0 | UIN: NBHLIP23155V012223.",
                        "Clause 1.1.1 (ReAssure+ / ReAssure Forever): Triggered immediately after the very first claim in a policy year. Once triggered, it provides UNLIMITED restoration (each restoration up to 100% of Base Sum Insured) for both unrelated and SAME illnesses for the lifetime of the policy.",
                        "Clause 1.1.2 (Booster+ Carry Forward): Any unutilized Base Sum Insured carries forward to the next policy year up to 5X (Bronze+) or 10X (Platinum+) of Base Sum Insured.",
                        "Clause 1.1.3 (Room Rent & ICU Limit): All room categories (including Single Private A/C, Deluxe, and Shared rooms, excluding Suite/Presidential Suite) are covered AT ACTUALS with no daily numeric cap. Zero proportionate deduction applies when staying in any non-suite room.",
                    ],
                    "table": [
                        ["Feature", "ReAssure 2.0 Bronze+", "ReAssure 2.0 Platinum+", "Trigger / Condition"],
                        ["Room Rent Cap", "All Rooms (Except Suite)", "All Rooms (Except Suite)", "No numeric room rent sub-limit"],
                        ["ReAssure Forever", "Unlimited (Up to Base SI/claim)", "Unlimited (Up to Base SI/claim)", "Triggers from 1st claim onwards"],
                        ["Booster+ Bonus", "Up to 5X Base SI", "Up to 10X Base SI", "Unutilized Base SI carries forward"],
                        ["Lock the Clock", "Included", "Included", "Pay entry-age bracket premium until claim"],
                        ["Safeguard+ Rider", "Optional Rider (Consumables)", "Optional Rider (Consumables)", "Covers all 68 Annexure-I items"],
                    ],
                }
            ],
        },
        {
            "h1": "# Section 2: Waiting Periods, Exclusions & Claim Rules",
            "sections": [
                {
                    "h2": "## 2.1 Waiting Periods & Maternity Status",
                    "paragraphs": [
                        "Clause 2.1.1 (Initial Waiting Period - Excl03): 30 days for all illnesses except accidental hospitalization.",
                        "Clause 2.1.2 (Specific Disease Waiting Period - Excl02): 24 months for listed surgeries and ailments (Cataract, Hernia, Joint Replacement, Benign Prostatic Hypertrophy, Gall Stones, Renal Calculi).",
                        "Clause 2.1.3 (Pre-Existing Disease Waiting Period - Excl01): 36 months of continuous coverage for all Pre-Existing Diseases (PED) under Platinum+ and Bronze+ variants.",
                        "Clause 2.1.4 (Maternity Exclusion): Maternity and newborn childbirth expenses are NOT covered under Niva Bupa ReAssure 2.0.",
                        "Clause 2.1.5 (Safeguard+ Benefit): When Safeguard+ add-on is opted, non-payable consumables (List I, II, III, IV of IRDAI Guidelines) are paid in full, and Booster+ balance is protected if total claims in a year are below Rs. 1,00,000.",
                    ],
                    "table": [
                        ["Clause Category", "Standard Rule in ReAssure 2.0", "Notes / Exceptions"],
                        ["PED Waiting Period", "36 Months", "Can be reduced via Personal Waiting Period modifier"],
                        ["Specific Illness Waiting", "24 Months", "Applies to 19 listed surgical/medical procedures"],
                        ["Maternity Waiting Period", "Not Covered", "Maternity is permanently excluded in ReAssure 2.0"],
                        ["Co-Payment", "0% Mandatory Co-Pay", "Optional 10% or 20% voluntary co-pay available"],
                        ["Cashless Pre-Auth TAT", "Within 60 Minutes", "Per IRDAI Master Circular & Niva Bupa Direct Claim"],
                    ],
                }
            ],
        },
    ]
    _render_multipage_pdf(niva_path, "Niva Bupa ReAssure 2.0 — Policy Wording", niva_pages)
    generated.append(niva_path)

    return generated


def generate_irdai_pdfs() -> list[Path]:
    """Generates the IRDAI Master Circular 2024 PDF and Annexure-I 68 Non-Payable Items PDF."""
    generated: list[Path] = []

    # 1. IRDAI Master Circular on Health Insurance Products (May 2024)
    mc_path = IRDAI_CIRCULARS_DIR / "IRDAI_Master_Circular_Health_Insurance_2024.pdf"
    mc_pages = [
        {
            "h1": "# Chapter 1: Moratorium Period & Non-Contestability of Claims",
            "sections": [
                {
                    "h2": "## 1.1 Reduction of Moratorium Period from 8 Years to 36 Months (5 Years to 3 Years)",
                    "paragraphs": [
                        "Circular Reference: IRDAI/HLT/CIR/PRO/84/05/2024 | Effective Year: 2024 | Issued by: Insurance Regulatory and Development Authority of India (IRDAI).",
                        "Clause 1.1 (36-Month Moratorium Rule): After completion of thirty-six (36) continuous months of coverage (3 years) under a health insurance policy across one or more insurers via portability, NO health insurance claim shall be contestable by the Insurer on grounds of non-disclosure or misrepresentation of a Pre-Existing Disease (PED), except in cases of proven established fraud.",
                        "Clause 1.2 (Maximum PED Waiting Period Cap): No health insurance product in India shall impose a Pre-Existing Disease (PED) waiting period exceeding 36 months of continuous coverage.",
                    ],
                    "table": [
                        ["Regulatory Provision", "Old IRDAI Rule", "New 2024 Master Circular Rule", "Legal Impact on Policyholder"],
                        ["Moratorium Period", "60 Months (5 Years)", "36 Months (3 Years)", "Insurer cannot reject claim for non-disclosure after 36M"],
                        ["Max PED Waiting Period", "48 Months (4 Years)", "36 Months (3 Years)", "All pre-existing diseases covered after 3 years"],
                        ["Free Look Period", "15 Days", "30 Days", "100% refund of premium if cancelled within 30 days"],
                        ["Grace Period (Renewal)", "15 Days (Monthly)", "15 Days (Monthly) / 30 Days (Annual)", "Coverage continuity maintained during grace period"],
                    ],
                }
            ],
        },
        {
            "h1": "# Chapter 2: Cashless Everywhere & Mandatory Turnaround Times (TAT)",
            "sections": [
                {
                    "h2": "## 2.1 1-Hour Pre-Authorization & 3-Hour Discharge Mandate",
                    "paragraphs": [
                        "Circular Reference: IRDAI/HLT/CIR/PRO/84/05/2024 | Topic: cashless_turnaround.",
                        "Clause 2.1 (1-Hour Cashless Authorization Rule): Every Insurer and Third Party Administrator (TPA) shall decide on cashless pre-authorization requests immediately and strictly within ONE (1) HOUR of receipt of the request from the hospital.",
                        "Clause 2.2 (3-Hour Final Discharge Rule): The Insurer shall grant final cashless discharge authorization within THREE (3) HOURS of receiving the discharge request and final bill from the hospital. In no case shall the policyholder be made to wait for discharge beyond 3 hours.",
                        "Clause 2.3 (Penalty for Delayed Discharge): If the Insurer delays discharge authorization beyond 3 hours, any additional hospital bed/room charges levied by the hospital for the extended stay shall be borne strictly by the Insurer from the Shareholders' Fund and NOT deducted from the Policyholder's Sum Insured.",
                        "Clause 2.4 (Death During Treatment): In the event of death of the insured patient during hospitalization, the insurer shall immediately settle the claim request and ensure the mortal remains are released from the hospital without delay.",
                    ],
                    "table": [
                        ["Cashless Milestone", "Mandatory IRDAI TAT", "Consequence of Insurer Breach"],
                        ["Emergency Pre-Authorization", "Within 1 Hour (60 Mins)", "Escalation to GRO / Bima Bharosa Portal"],
                        ["Final Discharge Approval", "Within 3 Hours (180 Mins)", "Insurer must pay extra hospital detention/room charges"],
                        ["No-Claim Bonus / Discount", "Reward for Claim-Free Year", "Option to take increased SI or discount in renewal premium"],
                    ],
                }
            ],
        },
        {
            "h1": "# Chapter 3: Grievance Redressal, Claim Rejection Rules & Insurance Ombudsman",
            "sections": [
                {
                    "h2": "## 3.1 Ban on Arbitrary Claim Rejection & Ombudsman Escalation",
                    "paragraphs": [
                        "Circular Reference: IRDAI/HLT/CIR/PRO/84/05/2024 | Topic: grievance_redressal.",
                        "Clause 3.1 (No Claim Rejection Without Committee Approval): No claim shall be repudiated/rejected directly by a TPA. Repudiation of any claim requires explicit approval from the Insurer's three-member Claims Review Committee (CRC).",
                        "Clause 3.2 (No Rejection for Want of Documents): No claim shall be closed or rejected merely for want of documents. Required documents must be called for at the time of admission itself.",
                        "Clause 3.3 (Insurance Ombudsman Award Compliance): If an insured escalates a complaint to the Insurance Ombudsman (for claims up to Rs. 50 Lakhs) and an Ombudsman Award is passed in favor of the policyholder, the Insurer MUST comply with the award within 30 days. Failure to comply attracts an unconditional penalty of Rs. 5,000 per day payable to the complainant, plus penal interest at 2% above the prevailing bank rate.",
                        "Clause 3.4 (Portability Rights): Policyholders may port their policy to another insurer at least 45 days before renewal with 100% credit for served waiting periods and accumulated No-Claim Bonus.",
                    ],
                }
            ],
        },
    ]
    _render_multipage_pdf(
        mc_path,
        "IRDAI Master Circular on Health Insurance Business 2024 (Ref: IRDAI/HLT/CIR/PRO/84/05/2024)",
        mc_pages,
    )
    generated.append(mc_path)

    # 2. IRDAI Annexure-I Standard List of 68 Non-Payable Consumables
    np_path = IRDAI_CIRCULARS_DIR / "IRDAI_Annexure_I_68_Non_Payable_Consumables.pdf"
    np_pages = [
        {
            "h1": "# IRDAI Annexure-I: Standard List of 68 Non-Payable Items & Subsumed Consumables",
            "sections": [
                {
                    "h2": "## Part A: Toiletries, Personal Comfort & Administrative Items (Items 1 to 35)",
                    "paragraphs": [
                        "Regulatory Standard: IRDAI Guidelines on Standardization in Health Insurance (Annexure-I).",
                        "Items marked as 'non_payable_unless_rider' are excluded in base policies unless the policy includes a Consumables Rider (such as HDFC ERGO Protect Benefit, Niva Bupa Safeguard+, or Star Extra Protect). Items marked as 'subsumed_in_room_charges' or 'subsumed_in_procedure_charges' CANNOT be billed separately by the hospital and must not be deducted from the patient if part of standard room/procedure tariffs.",
                    ],
                    "table": [
                        ["Item No.", "Item Name", "Payable Status", "IRDAI Billing Rule"],
                        ["1", "Baby Food", "non_payable_unless_rider", "Not payable under base inpatient claim unless rider active"],
                        ["2", "Baby Utilities Charges", "non_payable_unless_rider", "Not payable unless consumables rider is active"],
                        ["3", "Beauty Services", "non_payable_unless_rider", "Non-medical personal comfort item"],
                        ["4", "Belts / Braces", "payable_when_part_of_discharge", "Payable when prescribed for post-surgical stabilization"],
                        ["5", "Buds / Cotton Swabs", "subsumed_in_procedure_charges", "Subsumed in surgical/nursing charges; hospital cannot bill separately"],
                        ["12", "Crepe Bandage", "non_payable_unless_rider", "Non-payable unless covered by consumables rider"],
                        ["14", "Diapers / Underpads / Adult Diapers", "non_payable_unless_rider", "Non-payable unless consumables add-on is active"],
                        ["18", "Eye Pad / Eye Shield", "subsumed_in_procedure_charges", "Subsumed in ophthalmic procedure tariff"],
                        ["21", "Foot Cover / Shoe Cover", "subsumed_in_room_charges", "Infection control overhead; subsumed in room/OT charges"],
                        ["24", "Gown / Patient Gown", "subsumed_in_room_charges", "Subsumed in room rent; cannot be charged separately to patient"],
                    ],
                },
                {
                    "h2": "## Part B: Medical Disposables, Surgical Consumables & Kits (Items 36 to 68)",
                    "paragraphs": [
                        "Critical Rule for Hospital Bill Auditing: Hospitals frequently bill Surgical Gloves, Syringes, Nebulization Kits, Oxygen Masks, and Sanitizer separately. Under IRDAI Annexure-I, several infection-control items are subsumed in Room/OT charges, while patient-specific disposables require a Consumables Rider unless subsumed.",
                    ],
                    "table": [
                        ["Item No.", "Item Name", "Payable Status", "IRDAI Billing Rule"],
                        ["38", "Laundry Charges", "subsumed_in_room_charges", "Strictly subsumed in room rent; illegal to charge patient separately"],
                        ["42", "Nebulization Kit", "non_payable_unless_rider", "Payable under HDFC Protect / Niva Safeguard+ / Star Extra Protect"],
                        ["45", "Oxygen Cylinder (Outside Hospital)", "non_payable_unless_rider", "In-hospital oxygen is payable; portable cylinder non-payable without rider"],
                        ["47", "Pulse Oximeter Probe", "subsumed_in_room_charges", "Reusable monitoring sensor subsumed in ICU/Room charges"],
                        ["51", "Sanitizer / Hand Wash / Betadine", "subsumed_in_room_charges", "Hospital hygiene overhead; subsumed in room/nursing charges"],
                        ["54", "Surgical Blades / Scalpel", "subsumed_in_procedure_charges", "Subsumed in OT charges; payable if billed as part of surgery package"],
                        ["56", "Surgical Gloves / Examination Gloves", "non_payable_unless_rider", "Non-payable in base plans; 100% covered with Consumables Rider"],
                        ["59", "Syringes / IV Cannula / Infusion Set", "subsumed_in_procedure_charges", "Subsumed in nursing/procedure charges or covered via Consumables Rider"],
                        ["63", "Thermometer", "subsumed_in_room_charges", "Subsumed in ward/room charges"],
                        ["68", "Admission Kit / Discharge Kit / File Charges", "subsumed_in_room_charges", "Hospital administrative overhead; subsumed in room charges"],
                    ],
                },
            ],
        }
    ]
    _render_multipage_pdf(
        np_path,
        "IRDAI Annexure-I: Standard List of 68 Non-Payable Items & Subsumed Consumables",
        np_pages,
    )
    generated.append(np_path)

    return generated


def generate_eval_dataset() -> Path:
    """Generates 30 gold benchmark Q&A pairs for Ragas evaluation (data/eval_dataset.json)."""
    EVAL_DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    eval_items = [
        {
            "id": "eval_01",
            "category": "policy_qa",
            "question": "Does HDFC ERGO Optima Secure have any room rent capping or ICU sub-limit for a 10 Lakh sum insured?",
            "ground_truth": "No. Under HDFC ERGO Optima Secure (Clause 1.2), there is no room rent capping and no ICU daily sub-limit for any Sum Insured of Rs. 5 Lakhs and above. Insured members can occupy any room category at actuals without proportionate deduction.",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_02",
            "category": "policy_qa",
            "question": "How does the Secure Benefit work in HDFC ERGO Optima Secure?",
            "ground_truth": "Under Clause 1.1.1, the Secure Benefit doubles (adds 100% to) the Base Sum Insured instantly from Day 1 of policy inception at no extra cost. A Rs. 10 Lakh base policy immediately provides Rs. 20 Lakh coverage.",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_03",
            "category": "policy_qa",
            "question": "Are non-medical consumables like surgical gloves and nebulization kits covered in HDFC ERGO Optima Secure?",
            "ground_truth": "Yes. Clause 1.3.1 (Protect Benefit) is an in-built feature in HDFC ERGO Optima Secure that pays 100% for all 68 IRDAI Annexure-I non-payable consumable items during admissible inpatient hospitalization.",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_04",
            "category": "policy_qa",
            "question": "What is the waiting period for pre-existing diseases like diabetes and hypertension in HDFC ERGO Optima Secure?",
            "ground_truth": "Under Clause 2.1.3 (Code Excl01), Pre-Existing Diseases (PED) such as Diabetes Mellitus and Hypertension have a waiting period of 36 months of continuous coverage from policy inception.",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_05",
            "category": "policy_qa",
            "question": "What is the cataract and hernia waiting period under HDFC ERGO Optima Secure?",
            "ground_truth": "Under Clause 2.1.2 (Code Excl02), specific listed illnesses and surgeries including Cataract and Hernia have a 24-month continuous coverage waiting period.",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_06",
            "category": "policy_qa",
            "question": "Does HDFC ERGO Optima Secure cover maternity expenses?",
            "ground_truth": "No. Under Clause 2.1.4, HDFC ERGO Optima Secure does not cover maternity or childbirth expenses under the base policy (except ectopic pregnancy).",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_07",
            "category": "policy_qa",
            "question": "What is the eligible room category in Star Health Comprehensive and when does proportionate deduction apply?",
            "ground_truth": "Under Clause 1.1.1 and 1.1.2 of Star Health Comprehensive, the eligible room category is a Single Private A/C Room. If the insured chooses a higher room category (such as a Deluxe or Suite Room), proportionate deduction applies to all Associated Medical Expenses in the ratio of Eligible Room Rent to Actual Room Rent.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_08",
            "category": "policy_qa",
            "question": "Which hospital bill items are exempt from proportionate deduction under Star Health Comprehensive?",
            "ground_truth": "Under Clause 1.1.3 of Star Health Comprehensive, proportionate deduction is not applied to Pharmacy/Medicines, Implants/Stents, Diagnostics (if uniform tariff), or ICU charges.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_09",
            "category": "policy_qa",
            "question": "What is the maternity waiting period and sub-limit in Star Health Comprehensive?",
            "ground_truth": "Under Clause 2.1.1 of Star Health Comprehensive, maternity is covered after a 24-month waiting period when both self and spouse are insured under a floater plan. Normal delivery is capped at Rs. 30,000 to Rs. 50,000 and Caesarean section is capped at Rs. 40,000 to Rs. 1,00,000 depending on Sum Insured.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_10",
            "category": "policy_qa",
            "question": "Can the 36-month PED waiting period be reduced in Star Health Comprehensive?",
            "ground_truth": "Yes. Under Clause 2.1.3 of Star Health Comprehensive, an optional Buy-Back PED rider reduces the Pre-Existing Disease waiting period from 36 months to 12 months upon payment of additional premium.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_11",
            "category": "policy_qa",
            "question": "Is there a mandatory senior citizen co-payment in Star Health Comprehensive?",
            "ground_truth": "Yes. Under Clause 3.1.1 of Star Health Comprehensive, a mandatory 10% co-payment applies to each admissible claim for insured persons whose age at initial entry is 61 years or above.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 3,
        },
        {
            "id": "eval_12",
            "category": "policy_qa",
            "question": "How does ReAssure Forever restoration work in Niva Bupa ReAssure 2.0?",
            "ground_truth": "Under Clause 1.1.1 of Niva Bupa ReAssure 2.0, ReAssure Forever triggers immediately after the first claim in a policy year and provides unlimited restorations (each up to 100% of Base Sum Insured) for both unrelated and same illnesses for the lifetime of the policy.",
            "expected_source": "Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_13",
            "category": "policy_qa",
            "question": "What is the Booster+ feature in Niva Bupa ReAssure 2.0?",
            "ground_truth": "Under Clause 1.1.2, Booster+ carries forward any unutilized Base Sum Insured to the next policy year, accumulating up to 5X in Bronze+ and up to 10X in Platinum+.",
            "expected_source": "Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_14",
            "category": "policy_qa",
            "question": "What does the Safeguard+ rider cover in Niva Bupa ReAssure 2.0?",
            "ground_truth": "Under Clause 2.1.5, Safeguard+ pays 100% for all IRDAI non-payable consumables (List I, II, III, IV) and protects the Booster+ bonus from reduction if total claims in a policy year are below Rs. 1,00,000.",
            "expected_source": "Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_15",
            "category": "plan_comparison",
            "question": "Compare Star Health Comprehensive and Niva Bupa ReAssure 2.0 on maternity waiting period and restoration benefits.",
            "ground_truth": "Star Health Comprehensive covers maternity after a 24-month waiting period (up to Rs. 50,000 normal / Rs. 1,00,000 C-section) and provides 100% automatic restoration once per policy year. Niva Bupa ReAssure 2.0 does not cover maternity, but provides unlimited restoration (ReAssure Forever) from the first claim for both same and unrelated illnesses.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf,Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_16",
            "category": "plan_comparison",
            "question": "Compare HDFC ERGO Optima Secure and Star Health Comprehensive on room rent limits and consumables coverage.",
            "ground_truth": "HDFC ERGO Optima Secure has no room rent cap (any room at actuals) and includes Protect Benefit (covering all 68 consumables) in-built. Star Health Comprehensive caps room eligibility at a Single Private A/C Room (applying proportionate deduction for higher rooms) and excludes the 68 consumables unless the optional Star Extra Protect rider is purchased.",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf,Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_17",
            "category": "plan_comparison",
            "question": "Compare senior citizen co-payment rules across HDFC ERGO Optima Secure, Star Health Comprehensive, and Niva Bupa ReAssure 2.0.",
            "ground_truth": "HDFC ERGO Optima Secure and Niva Bupa ReAssure 2.0 have 0% mandatory age-based co-payment across all entry ages. Star Health Comprehensive enforces a mandatory 10% co-payment for policyholders entering at age 61 or above.",
            "expected_source": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf,Star_Health_Comprehensive_Policy_Wording.pdf,Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_18",
            "category": "claim_calculation",
            "question": "If my policy has an allowed room rent cap of Rs. 5,000/day, I choose a room costing Rs. 10,000/day, and my eligible associated medical bill is Rs. 1,00,000 with Rs. 10,000 deductible, what is my payable claim amount?",
            "ground_truth": "Using the proportionate deduction formula: Payable before deductible = 1,00,000 * (5,000 / 10,000) = Rs. 50,000. Subtracting the Rs. 10,000 deductible leaves a net payable claim amount of Rs. 40,000 (and Rs. 60,000 out-of-pocket).",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_19",
            "category": "claim_calculation",
            "question": "Under Star Health Comprehensive, if Eligible Room Rent is Rs. 6,000/day, Actual Room Rent chosen is Rs. 9,000/day, Surgeon + OT charges are Rs. 90,000, and Pharmacy/Medicines cost Rs. 30,000, how much will the insurer pay?",
            "ground_truth": "Surgeon + OT charges undergo proportionate deduction: 90,000 * (6,000 / 9,000) = Rs. 60,000. Under Clause 1.1.3, Pharmacy/Medicines (Rs. 30,000) are exempt from proportionate deduction and paid in full. Total payable for these components = Rs. 60,000 + Rs. 30,000 = Rs. 90,000.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_20",
            "category": "claim_calculation",
            "question": "A 65-year-old who entered Star Health Comprehensive at age 62 has an admissible hospital bill of Rs. 2,00,000 in a Single Private A/C Room. How much is the mandatory co-payment deduction?",
            "ground_truth": "Because the insured entered at age 62 (61 or above), a mandatory 10% co-payment applies under Clause 3.1.1. The co-payment deduction is 10% of Rs. 2,00,000 = Rs. 20,000, and the net payable claim is Rs. 1,80,000.",
            "expected_source": "Star_Health_Comprehensive_Policy_Wording.pdf",
            "expected_page": 3,
        },
        {
            "id": "eval_21",
            "category": "regulatory_grievance",
            "question": "What is the IRDAI 2024 Master Circular rule on the moratorium period for health insurance policies?",
            "ground_truth": "Under Circular IRDAI/HLT/CIR/PRO/84/05/2024 (Clause 1.1), the moratorium period is 36 continuous months (3 years), reduced from 60 months. After 36 months of continuous coverage, no claim can be rejected by an insurer on grounds of non-disclosure or misrepresentation except in cases of proven fraud.",
            "expected_source": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_22",
            "category": "regulatory_grievance",
            "question": "My insurer rejected my claim after 4 years of continuous policy renewals citing non-disclosure of hypertension at policy purchase. Is this legal under IRDAI rules?",
            "ground_truth": "No. Since 4 years (48 months) exceeds the mandatory 36-month moratorium period under IRDAI Master Circular IRDAI/HLT/CIR/PRO/84/05/2024 (Clause 1.1), the insurer cannot repudiate the claim for alleged non-disclosure of hypertension unless it proves established fraud.",
            "expected_source": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_23",
            "category": "regulatory_grievance",
            "question": "What are the mandatory IRDAI timelines for cashless pre-authorization and hospital discharge?",
            "ground_truth": "Under IRDAI Master Circular IRDAI/HLT/CIR/PRO/84/05/2024 (Clauses 2.1 and 2.2), insurers must decide on cashless pre-authorization requests within 1 hour (60 minutes) and grant final discharge authorization within 3 hours (180 minutes) of receiving the discharge request from the hospital.",
            "expected_source": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_24",
            "category": "regulatory_grievance",
            "question": "Who pays if the hospital charges extra room rent because the insurer took 7 hours to approve cashless discharge?",
            "ground_truth": "Under Clause 2.3 of IRDAI Master Circular 2024, if the insurer delays discharge authorization beyond the mandatory 3-hour limit, any additional hospital bed/room charges must be paid directly by the insurer from its Shareholders' Fund and cannot be deducted from the policyholder's Sum Insured or billed to the patient.",
            "expected_source": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
            "expected_page": 2,
        },
        {
            "id": "eval_25",
            "category": "regulatory_grievance",
            "question": "Can a Third Party Administrator (TPA) reject a health insurance claim on its own?",
            "ground_truth": "No. Under Clause 3.1 of IRDAI Master Circular 2024, no claim can be rejected directly by a TPA. Every claim repudiation requires explicit approval from the insurer's three-member Claims Review Committee (CRC).",
            "expected_source": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
            "expected_page": 3,
        },
        {
            "id": "eval_26",
            "category": "regulatory_grievance",
            "question": "What penalty applies if an insurer fails to honour an Insurance Ombudsman award within 30 days?",
            "ground_truth": "Under Clause 3.3 of IRDAI Master Circular 2024, if an insurer fails to comply with an Insurance Ombudsman Award within 30 days, it must pay a penalty of Rs. 5,000 per day to the complainant plus penal interest at 2% above the prevailing bank rate.",
            "expected_source": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
            "expected_page": 3,
        },
        {
            "id": "eval_27",
            "category": "regulatory_grievance",
            "question": "What is the free look period under the IRDAI Master Circular 2024?",
            "ground_truth": "Under Clause 1.2 (Table) of the IRDAI Master Circular 2024, policyholders get a 30-day Free Look Period from policy receipt to review terms and cancel for a 100% refund (subject to standard pro-rata risk/stamp duty adjustments if no claim was made).",
            "expected_source": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_28",
            "category": "policy_qa",
            "question": "Can a hospital charge me separately for patient gown, laundry charges, and pulse oximeter probe?",
            "ground_truth": "No. Under IRDAI Annexure-I (Items 24, 38, and 47), Patient Gown, Laundry Charges, and Pulse Oximeter Probe are classified as 'subsumed_in_room_charges'. They are included in the room/ICU tariff and cannot be billed separately to the patient.",
            "expected_source": "IRDAI_Annexure_I_68_Non_Payable_Consumables.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_29",
            "category": "policy_qa",
            "question": "How are surgical gloves (Item 56) and nebulization kits (Item 42) treated under IRDAI Annexure-I?",
            "ground_truth": "Under IRDAI Annexure-I, Nebulization Kit (Item 42) and Surgical Gloves (Item 56) have status 'non_payable_unless_rider'. They are not payable under standard base policies without a consumables cover, but are 100% payable when the policy has a consumables rider (such as HDFC Protect Benefit, Niva Safeguard+, or Star Extra Protect).",
            "expected_source": "IRDAI_Annexure_I_68_Non_Payable_Consumables.pdf",
            "expected_page": 1,
        },
        {
            "id": "eval_30",
            "category": "policy_qa",
            "question": "Are admission kit and file charges (Item 68) payable or deductible from the patient?",
            "ground_truth": "Under IRDAI Annexure-I (Item 68), Admission Kit / Discharge Kit / File Charges have status 'subsumed_in_room_charges'. They are hospital administrative overhead subsumed in room rent and cannot be charged separately to the patient.",
            "expected_source": "IRDAI_Annexure_I_68_Non_Payable_Consumables.pdf",
            "expected_page": 1,
        },
    ]

    EVAL_DATASET_PATH.write_text(json.dumps(eval_items, indent=2), encoding="utf-8")
    return EVAL_DATASET_PATH


def generate_all_seed_data() -> dict[str, Any]:
    """Generates all seed policy PDFs, IRDAI regulatory PDFs, and the Ragas evaluation dataset."""
    policy_pdfs = generate_policy_pdfs()
    irdai_pdfs = generate_irdai_pdfs()
    eval_path = generate_eval_dataset()
    return {
        "policy_pdfs": [str(p) for p in policy_pdfs],
        "irdai_pdfs": [str(p) for p in irdai_pdfs],
        "eval_dataset": str(eval_path),
    }


if __name__ == "__main__":
    summary = generate_all_seed_data()
    print(json.dumps(summary, indent=2))

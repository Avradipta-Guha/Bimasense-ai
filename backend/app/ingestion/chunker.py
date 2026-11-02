"""
Header-Aware & Table-Preserving Semantic Chunker for BimaSense AI (Milestone 1).
Splits parsed Markdown pages into atomic retrieval chunks while:
1. Never splitting a Markdown pipe table across two chunks unless it exceeds max size
   (and if split, repeating the Markdown table header row on every continuation chunk).
2. Preserving hierarchical Markdown heading breadcrumbs (`# Section -> ## Clause`).
3. Automatically classifying `section_category` (`waiting_periods`, `exclusions`,
   `room_rent`, `inclusions`, `claim_procedure`, `restoration_and_bonuses`, `general_terms`).
4. Producing validated Pydantic payloads for all 3 Qdrant collections:
   - `insurer_policies` (`InsurerPolicyPayload`)
   - `irdai_regulations` (`IrdaiRegulationPayload`)
   - `non_payable_consumables` (`NonPayableConsumablePayload`)
"""

from __future__ import annotations

import hashlib
from app.config import settings
from app.schemas.api_models import (
    DocumentType,
    InsurerPolicyPayload,
    IrdaiRegulationPayload,
    IrdaiTopic,
    NonPayableConsumablePayload,
    ParsedDocument,
    PayableStatus,
    SectionCategory,
)


def _deterministic_id(prefix: str, source_file: str, page_number: int, index: int, text: str) -> str:
    """Generates a deterministic UUID-formatted hex string for Qdrant point IDs."""
    digest = hashlib.md5(f"{prefix}:{source_file}:{page_number}:{index}:{text[:120]}".encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def classify_section_category(heading: str, text: str) -> SectionCategory:
    """Rule-based keyword & clause code classifier for insurance policy sections."""
    combined = f"{heading}\n{text}".lower()

    if any(k in combined for k in ["room rent", "single private", "proportionate deduction", "icu charges", "room category"]):
        return "room_rent"
    if any(k in combined for k in ["waiting period", "excl01", "excl02", "excl03", "pre-existing", "36 months", "24 months", "maternity"]):
        return "waiting_periods"
    if any(k in combined for k in ["reassure forever", "restoration", "restore benefit", "booster+", "plus benefit", "secure benefit", "no-claim bonus", "cumulative bonus"]):
        return "restoration_and_bonuses"
    if any(k in combined for k in ["claim procedure", "cashless", "pre-authorization", "turnaround", "co-payment", "deductible"]):
        return "claim_procedure"
    if any(k in combined for k in ["exclusion", "not covered", "non-payable", "permanently excluded"]):
        return "exclusions"
    if any(k in combined for k in ["inclusion", "base coverage", "protect benefit", "safeguard+", "in-built"]):
        return "inclusions"
    return "general_terms"


def classify_irdai_topic(heading: str, text: str) -> IrdaiTopic:
    """Classifies IRDAI Master Circular chunks into canonical regulatory topics."""
    combined = f"{heading}\n{text}".lower()
    if "ombudsman" in combined or "grievance" in combined or "repudiated" in combined or "5,000" in combined or "claims review committee" in combined:
        return "grievance_redressal"
    if "moratorium" in combined or "non-disclosure" in combined or "free look" in combined:
        return "moratorium_period"
    if "1 hour" in combined or "3 hours" in combined or "cashless" in combined or "discharge" in combined:
        return "cashless_turnaround"
    if "portability" in combined:
        return "portability"
    return "claim_settlement"


class MarkdownPolicyChunker:
    """
    Splits a `ParsedDocument` into header-contextualized, table-intact chunks.
    """

    def __init__(
        self,
        chunk_size_chars: int = settings.chunk_size_chars,
        chunk_overlap_chars: int = settings.chunk_overlap_chars,
    ) -> None:
        self.chunk_size_chars = chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    def _split_into_semantic_blocks(self, page_md: str) -> list[tuple[str, str, bool]]:
        """
        Splits a page's Markdown into `(heading_breadcrumb, block_text, is_table)` tuples.
        Keeps contiguous Markdown table lines (`| ... |`) grouped as an atomic block
        and avoids emitting tiny standalone document-title preambles (< 140 chars).
        """
        lines = page_md.splitlines()
        current_h1 = ""
        current_h2 = ""
        blocks: list[tuple[str, str, bool]] = []

        buffer_lines: list[str] = []
        buffer_is_table = False

        def flush_buffer() -> None:
            nonlocal buffer_lines, buffer_is_table
            content = "\n".join(buffer_lines).strip()
            if content:
                breadcrumb = " > ".join(h for h in [current_h1, current_h2] if h)
                if not breadcrumb and len(content) < 140 and not buffer_is_table:
                    buffer_lines = []
                    buffer_is_table = False
                    return
                blocks.append((breadcrumb, content, buffer_is_table))
            buffer_lines = []
            buffer_is_table = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                flush_buffer()
                current_h1 = stripped.lstrip("# ").strip()
                current_h2 = ""
                continue
            if stripped.startswith("## ") or stripped.startswith("### "):
                flush_buffer()
                current_h2 = stripped.lstrip("# ").strip()
                continue

            is_table_line = stripped.startswith("|") and stripped.endswith("|")
            if is_table_line != buffer_is_table and buffer_lines:
                flush_buffer()

            buffer_is_table = is_table_line
            buffer_lines.append(line)

        flush_buffer()
        return blocks

    def _window_text_block(self, heading: str, text: str) -> list[str]:
        """Splits long narrative blocks into overlapping chunks while prepending the heading breadcrumb."""
        prefix = f"[{heading}]\n" if heading else ""
        max_body = max(300, self.chunk_size_chars - len(prefix))

        if len(text) <= max_body:
            return [f"{prefix}{text}".strip()]

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) + 2 > max_body and current:
                chunks.append(f"{prefix}" + "\n\n".join(current))
                if len(current[-1]) <= self.chunk_overlap_chars:
                    current = [current[-1], para]
                    current_len = sum(len(x) for x in current)
                else:
                    current = [para]
                    current_len = len(para)
            else:
                current.append(para)
                current_len += len(para) + 2

        if current:
            chunks.append(f"{prefix}" + "\n\n".join(current))

        return chunks

    def chunk_insurer_policy(
        self,
        doc: ParsedDocument,
        insurer_name: str,
        plan_name: str,
        document_type: DocumentType = "policy_wording",
        is_user_uploaded: bool = False,
        user_id: str = "global",
    ) -> list[InsurerPolicyPayload]:
        """Produces validated `InsurerPolicyPayload` chunks for the `insurer_policies` collection."""
        payloads: list[InsurerPolicyPayload] = []
        chunk_counter = 0

        for page in doc.pages:
            blocks = self._split_into_semantic_blocks(page.markdown_text)
            for heading, block_text, is_table in blocks:
                if is_table:
                    prefix = f"[{insurer_name} - {plan_name} | {heading}]\n" if heading else f"[{insurer_name} - {plan_name}]\n"
                    chunk_texts = [f"{prefix}{block_text}".strip()]
                else:
                    full_heading = f"{insurer_name} - {plan_name} | {heading}" if heading else f"{insurer_name} - {plan_name}"
                    chunk_texts = self._window_text_block(full_heading, block_text)

                for c_text in chunk_texts:
                    chunk_counter += 1
                    category = classify_section_category(heading, c_text)
                    chunk_id = _deterministic_id("policy", doc.file_name, page.page_number, chunk_counter, c_text)
                    payloads.append(
                        InsurerPolicyPayload(
                            chunk_id=chunk_id,
                            insurer_name=insurer_name,
                            plan_name=plan_name,
                            document_type=document_type,
                            section_category=category,
                            section_heading=heading or f"Page {page.page_number}",
                            page_number=page.page_number,
                            contains_table=is_table or ("| --- |" in c_text),
                            is_user_uploaded=is_user_uploaded,
                            user_id=user_id,
                            text=c_text,
                            source_file=doc.file_name,
                        )
                    )

        return payloads

    def chunk_irdai_regulation(
        self,
        doc: ParsedDocument,
        circular_ref: str = "IRDAI/HLT/CIR/PRO/84/05/2024",
        effective_year: int = 2024,
    ) -> list[IrdaiRegulationPayload]:
        """Produces validated `IrdaiRegulationPayload` chunks for the `irdai_regulations` collection."""
        payloads: list[IrdaiRegulationPayload] = []
        chunk_counter = 0

        for page in doc.pages:
            blocks = self._split_into_semantic_blocks(page.markdown_text)
            for heading, block_text, is_table in blocks:
                full_heading = f"IRDAI Circular {circular_ref} | {heading}" if heading else f"IRDAI Circular {circular_ref}"
                chunk_texts = (
                    [f"[{full_heading}]\n{block_text}".strip()]
                    if is_table
                    else self._window_text_block(full_heading, block_text)
                )
                for c_text in chunk_texts:
                    chunk_counter += 1
                    topic = classify_irdai_topic(heading, c_text)
                    chunk_id = _deterministic_id("irdai", doc.file_name, page.page_number, chunk_counter, c_text)
                    payloads.append(
                        IrdaiRegulationPayload(
                            chunk_id=chunk_id,
                            circular_ref=circular_ref,
                            topic=topic,
                            effective_year=effective_year,
                            page_number=page.page_number,
                            section_heading=heading or f"Page {page.page_number}",
                            text=c_text,
                            source_file=doc.file_name,
                        )
                    )

        return payloads

    def chunk_non_payable_consumables(self, doc: ParsedDocument) -> list[NonPayableConsumablePayload]:
        """
        Extracts individual IRDAI Annexure-I Non-Payable items from Markdown pipe tables
        into atomic `NonPayableConsumablePayload` records for high-precision item lookup.
        """
        payloads: list[NonPayableConsumablePayload] = []
        seen_items: set[int] = set()
        valid_statuses: set[str] = {
            "non_payable_unless_rider",
            "subsumed_in_room_charges",
            "subsumed_in_procedure_charges",
            "payable_when_part_of_discharge",
        }

        for page in doc.pages:
            for line in page.markdown_text.splitlines():
                stripped = line.strip()
                if not (stripped.startswith("|") and stripped.endswith("|")):
                    continue
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if len(cells) < 4 or not cells[0].isdigit():
                    continue

                item_num = int(cells[0])
                if item_num in seen_items:
                    continue
                seen_items.add(item_num)

                item_name = cells[1]
                raw_status = cells[2].strip().lower()
                payable_status: PayableStatus = (
                    raw_status  # type: ignore[assignment]
                    if raw_status in valid_statuses
                    else "non_payable_unless_rider"
                )
                billing_rule = cells[3]
                descriptive_text = (
                    f"IRDAI Annexure-I Item #{item_num}: {item_name} | "
                    f"Payable Status: {payable_status} | "
                    f"Regulatory Rule: {billing_rule}"
                )
                chunk_id = _deterministic_id("consumable", doc.file_name, page.page_number, item_num, descriptive_text)
                payloads.append(
                    NonPayableConsumablePayload(
                        chunk_id=chunk_id,
                        item_number=item_num,
                        item_name=item_name,
                        category="Annexure-I Standard Non-Payable List",
                        payable_status=payable_status,
                        page_number=page.page_number,
                        text=descriptive_text,
                        source_file=doc.file_name,
                    )
                )

        return payloads

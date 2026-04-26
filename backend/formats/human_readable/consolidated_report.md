# Consolidated Daily Report — VNRVJIET

> **Pipeline**: Deterministic extraction + LLM narrative summarization  
> **SDK**: `google-genai` (gemini-2.5-flash / 2.0-flash)

---

## Section Order (in generated DOCX)

| # | Section | Source | Method |
|---|---------|--------|--------|
| 1 | **Staff Attendance** | `Staff & Student attendance report` | Deterministic — computes Present & % from On Rolls/Absent |
| 2 | **MTP Highlights & Batch Pills** | `Daily Report-MTP.docx` (nested tables) | Deterministic — nested table traversal |
| 3 | **Department Highlights** | All 16 dept reports (events/seminars) | LLM narrative summarization |
| 4 | **Staff & Student Participation** | All 16 dept reports | LLM narrative summarization |
| 5 | **Staff Changes** | All 16 dept reports | Deterministic |
| 6 | **Classwork Adjustments** | All 16 dept reports | Deterministic (count only) |
| 7 | **Library Services** | `Library DAILY REPORT.docx` | Deterministic |
| 8 | **Infrastructure Issues** | All 16 dept reports | Deterministic (LAST section) |

---

## Staff Attendance Table (Section 1)

**Columns**: S.No · Dept. · Category · On Rolls · Present · Absent · %

- **Present** = On Rolls − Absent (computed, not from source)
- **%** = Present / On Rolls × 100 (computed)
- **DQI / Performance columns**: EXCLUDED
- **Student attendance**: EXCLUDED
- **Summary rows**: Teaching Total, Non-Teaching Total, Grand Total

---

## MTP Section (Section 2)

Extracted from nested tables inside the MTP daily report:

- **MTP Narrative**: Placement drives, PPTs, hiring updates from Section IV
- **Batch Pills Open Summary**: Department-wise placement pill counts table

Both are extracted deterministically from nested DOCX table cells.

---

## Notes

- **English dept** may fail extraction due to corrupt embedded images (Bad CRC-32)
- **LLM is ONLY used** for narrative summarization of events and participation
- **All numbers** (attendance, library, infrastructure) are 100% deterministic
- **Model fallback**: gemini-2.5-flash → gemini-2.0-flash → gemini-2.0-flash-lite

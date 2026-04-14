"""
Post-Processor for Consolidated Report JSON

Runs AFTER AI consolidation and BEFORE DOCX generation.
Applies the following clean-up rules:

1. Normalize all event names  (Title Case, strip quotes, trim spaces)
2. Deduplicate events         (group by normalized name + date)
3. Remove redundant summaries (if summary just restates the title metadata)
4. Group identical participation entries under one event
5. Strip "Other:" prefixes
6. Remove placeholder / template text
7. Final validation pass
"""

import re
from collections import defaultdict


# ── Known placeholders that should be stripped ─────────────────────────────────

PLACEHOLDER_PATTERNS = [
    re.compile(r"^name of the department$", re.IGNORECASE),
    re.compile(r"^department name$", re.IGNORECASE),
    re.compile(r"^enter .*here$", re.IGNORECASE),
    re.compile(r"^n/?a$", re.IGNORECASE),
    re.compile(r"^-+$"),
    re.compile(r"^nil$", re.IGNORECASE),
    re.compile(r"^none$", re.IGNORECASE),
    re.compile(r"^xx+$", re.IGNORECASE),
]


def _is_placeholder(text: str) -> bool:
    """Return True if the text matches a known placeholder pattern."""
    if not text or not text.strip():
        return True
    stripped = text.strip()
    return any(p.match(stripped) for p in PLACEHOLDER_PATTERNS)


# ── Event name normalization ──────────────────────────────────────────────────

def normalize_event_name(event_name: str) -> str:
    """
    Normalize an event name for consistent display and grouping.

    - Remove surrounding and embedded quotation marks
    - Collapse whitespace
    - Convert to Title Case
    - Trim leading/trailing spaces
    """
    if not event_name:
        return ""

    name = event_name.strip()

    # Remove all types of quotation marks
    name = re.sub(r'["""\u2018\u2019\u201C\u201D\'`]', '', name)

    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)

    # Title Case
    name = name.title()

    # Fix common title-case artefacts: "And" -> "and", "Of" -> "of", etc.
    # but only when they are mid-title (not first word)
    small_words = {"A", "An", "And", "As", "At", "By", "For", "In",
                   "Is", "Of", "On", "Or", "The", "To", "With"}
    words = name.split()
    if len(words) > 1:
        normalized_words = [words[0]]
        for w in words[1:]:
            if w in small_words:
                normalized_words.append(w.lower())
            else:
                normalized_words.append(w)
        name = " ".join(normalized_words)

    return name.strip()


def _event_group_key(event: dict) -> str:
    """Create a grouping key from normalised event name + date."""
    name = normalize_event_name(event.get("name", ""))
    date = (event.get("date") or "").strip().lower()
    return f"{name}||{date}"


# ── Summary deduplication ─────────────────────────────────────────────────────

def _summary_is_redundant(event: dict) -> bool:
    """
    Return True if the summary merely restates information already present
    in the event title + metadata fields (date, duration, resource person).
    """
    summary = (event.get("summary") or "").strip().lower()
    if not summary:
        return True  # nothing to render

    name = (event.get("name") or "").strip().lower()
    date = (event.get("date") or "").strip().lower()
    duration = (event.get("duration") or "").strip().lower()
    resource_person = (event.get("resource_person") or "").strip().lower()

    # Strip punctuation from both for fuzzy comparison
    def _clean(s: str) -> str:
        return re.sub(r'[^a-z0-9 ]', '', s).strip()

    clean_summary = _clean(summary)
    clean_name = _clean(name)

    # If the summary is essentially the event name (possibly with date/duration tacked on)
    if not clean_summary:
        return True
    if clean_name and clean_summary.startswith(clean_name):
        remainder = clean_summary[len(clean_name):].strip()
        # remainder is empty or just date/duration fragments
        if not remainder:
            return True
        tokens = set(remainder.split())
        meta_tokens = set()
        if date:
            meta_tokens.update(_clean(date).split())
        if duration:
            meta_tokens.update(_clean(duration).split())
        if resource_person:
            meta_tokens.update(_clean(resource_person).split())
        # Filler words
        meta_tokens.update({"on", "from", "to", "for", "the", "a", "an",
                            "was", "is", "by", "at", "in", "with", "held",
                            "conducted", "organised", "organized", "during",
                            "and", "of", "days", "day"})
        if tokens.issubset(meta_tokens):
            return True

    return False


# ── Strip "Other:" prefix ────────────────────────────────────────────────────

def _strip_other_prefix(text: str) -> str:
    """Remove leading 'Other:' or '• Other:' prefix from a string."""
    if not text:
        return text
    cleaned = re.sub(r'^(\s*•?\s*)?other\s*:\s*', '', text, flags=re.IGNORECASE)
    return cleaned.strip()


# ── Merge duplicate events ───────────────────────────────────────────────────

def _merge_events(events: list[dict]) -> list[dict]:
    """
    Group events by (normalized_name, date).
    For duplicate events, merge participant counts and keep the richest metadata.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        key = _event_group_key(ev)
        groups[key].append(ev)

    merged = []
    for key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
        else:
            # Pick the event entry with the most metadata as the base
            base = max(group, key=lambda e: len([
                v for v in e.values() if v is not None and v != ""
            ]))
            base = dict(base)  # shallow copy

            # Merge participant counts by summing
            total_internal = 0
            total_external = 0
            has_internal = False
            has_external = False
            for e in group:
                if e.get("participants_internal") is not None:
                    total_internal += e["participants_internal"]
                    has_internal = True
                if e.get("participants_external") is not None:
                    total_external += e["participants_external"]
                    has_external = True

            if has_internal:
                base["participants_internal"] = total_internal
            if has_external:
                base["participants_external"] = total_external

            # Use the best importance rating
            importance_rank = {"high": 3, "medium": 2, "low": 1}
            best_importance = max(
                (e.get("importance", "low") for e in group),
                key=lambda x: importance_rank.get(x, 0)
            )
            base["importance"] = best_importance

            # Use longest summary
            best_summary = max(
                (e.get("summary", "") or "" for e in group),
                key=len
            )
            base["summary"] = best_summary

            merged.append(base)

    return merged


# ── Group participation entries by event ─────────────────────────────────────

def _group_participation(entries: list[dict]) -> list[dict]:
    """
    Group participation entries by (normalized event name, date).
    Combine participants into a list under a single event entry.
    """
    if not entries:
        return entries

    groups: dict[str, dict] = {}
    order: list[str] = []

    for entry in entries:
        event_name = normalize_event_name(entry.get("event", ""))
        date_str = (entry.get("date") or "").strip().lower()
        key = f"{event_name}||{date_str}"

        if key not in groups:
            groups[key] = {
                "event": event_name,
                "date": entry.get("date", ""),
                "venue": entry.get("venue"),
                "participants": [],
            }
            order.append(key)

        participant = {
            "name": entry.get("name", ""),
            "dept": entry.get("dept", ""),
        }
        # Add role/achievement if present
        if entry.get("role"):
            participant["role"] = entry["role"]
        if entry.get("achievement"):
            participant["achievement"] = entry["achievement"]
        if entry.get("summary"):
            participant["summary"] = entry["summary"]

        groups[key]["participants"].append(participant)

    # Flatten back to entries, but with grouped participant info
    result = []
    for key in order:
        group = groups[key]
        participants = group["participants"]

        if len(participants) == 1:
            # Single participant — keep original format
            p = participants[0]
            result.append({
                "name": p.get("name", ""),
                "dept": p.get("dept", ""),
                "event": group["event"],
                "role": p.get("role", ""),
                "achievement": p.get("achievement", ""),
                "date": group["date"],
                "venue": group.get("venue"),
                "summary": p.get("summary", ""),
            })
        else:
            # Multiple participants — mark as grouped
            result.append({
                "name": "",  # no single name
                "dept": "",
                "event": group["event"],
                "role": "",
                "achievement": "",
                "date": group["date"],
                "venue": group.get("venue"),
                "summary": "",
                "_grouped_participants": participants,
            })

    return result


# ── Main post-processing entry point ─────────────────────────────────────────

def post_process(report: dict) -> dict:
    """
    Clean, deduplicate, and normalise the consolidated report JSON.
    This must be called AFTER AI consolidation and BEFORE DOCX generation.
    """
    # ── 1. Clean department highlights ────────────────────────────────────────
    highlights = report.get("department_highlights", [])
    cleaned_highlights = []

    for dept_block in highlights:
        dept_name = dept_block.get("dept", "")
        dept_code = dept_block.get("dept_code", "")

        # Skip placeholder departments
        if _is_placeholder(dept_name) or _is_placeholder(dept_code):
            continue

        # Normalize event names
        events = dept_block.get("events", [])
        for ev in events:
            ev["name"] = normalize_event_name(ev.get("name", ""))

        # Deduplicate events within this department
        events = _merge_events(events)

        # Remove redundant summaries
        for ev in events:
            if _summary_is_redundant(ev):
                ev["summary"] = ""

        # Filter out placeholder events
        events = [
            ev for ev in events
            if not _is_placeholder(ev.get("name", ""))
        ]

        # Clean other_matters
        other_matters = dept_block.get("other_matters", [])
        cleaned_matters = []
        for matter in other_matters:
            if isinstance(matter, str):
                matter = _strip_other_prefix(matter)
                if matter and not _is_placeholder(matter):
                    cleaned_matters.append(matter)
            elif isinstance(matter, dict):
                desc = _strip_other_prefix(matter.get("description", ""))
                if desc and not _is_placeholder(desc):
                    matter["description"] = desc
                    cleaned_matters.append(matter)

        if events or cleaned_matters:
            cleaned_highlights.append({
                "dept": dept_name,
                "dept_code": dept_code,
                "events": events,
                "other_matters": cleaned_matters,
            })

    report["department_highlights"] = cleaned_highlights

    # ── 2. Group participation entries ────────────────────────────────────────
    staff_p = report.get("staff_participation", [])
    student_p = report.get("student_participation", [])

    # Normalize event names in participation
    for entry in staff_p:
        entry["event"] = normalize_event_name(entry.get("event", ""))
        # Strip placeholder names
        if _is_placeholder(entry.get("name", "")):
            entry["name"] = ""
    for entry in student_p:
        entry["event"] = normalize_event_name(entry.get("event", ""))
        if _is_placeholder(entry.get("name", "")):
            entry["name"] = ""

    report["staff_participation"] = _group_participation(staff_p)
    report["student_participation"] = _group_participation(student_p)

    # ── 3. Clean other sections ───────────────────────────────────────────────

    # Infrastructure: remove placeholders
    infra = report.get("infrastructure_issues", [])
    report["infrastructure_issues"] = [
        i for i in infra
        if not _is_placeholder(i.get("description", ""))
        and not _is_placeholder(i.get("dept", ""))
    ]

    # Staff changes: remove placeholders
    changes = report.get("staff_changes", [])
    report["staff_changes"] = [
        c for c in changes
        if not _is_placeholder(c.get("name", ""))
    ]

    # Incidents: remove placeholders
    incidents = report.get("incidents", [])
    report["incidents"] = [
        inc for inc in incidents
        if not _is_placeholder(inc.get("brief", ""))
    ]

    # Classwork adjustments: remove zero-count and placeholders
    adjustments = report.get("classwork_adjustments", [])
    report["classwork_adjustments"] = [
        adj for adj in adjustments
        if not _is_placeholder(adj.get("dept", ""))
        and adj.get("count") is not None
        and adj.get("count", 0) > 0
    ]

    # ── 4. Cross-section event deduplication ──────────────────────────────────
    # Check that no event appears in both department_highlights AND participation
    # (This is a validation step — log but don't remove from highlights since
    #  highlights give context, participation gives names)

    # ── 5. Final validation ───────────────────────────────────────────────────
    _validate(report)

    return report


def _validate(report: dict):
    """
    Run final validation checks. Prints warnings for any issues found.
    Does NOT raise exceptions — the report is still generated.
    """
    issues = []

    # Check: no duplicate events within a department
    for dept_block in report.get("department_highlights", []):
        seen_events = set()
        for ev in dept_block.get("events", []):
            key = _event_group_key(ev)
            if key in seen_events:
                issues.append(
                    f"Duplicate event in {dept_block.get('dept', '?')}: "
                    f"{ev.get('name', '?')}"
                )
            seen_events.add(key)

    # Check: no "Other:" prefix remaining
    for dept_block in report.get("department_highlights", []):
        for matter in dept_block.get("other_matters", []):
            text = matter if isinstance(matter, str) else matter.get("description", "")
            if re.match(r'^\s*other\s*:', text, re.IGNORECASE):
                issues.append(f"'Other:' prefix found in: {text[:60]}")

    # Check: no placeholder values
    for dept_block in report.get("department_highlights", []):
        if _is_placeholder(dept_block.get("dept", "")):
            issues.append(f"Placeholder department name: {dept_block.get('dept')}")
        for ev in dept_block.get("events", []):
            if _is_placeholder(ev.get("name", "")):
                issues.append(f"Placeholder event name: {ev.get('name')}")

    if issues:
        print(f"[POST-PROCESSOR] Validation found {len(issues)} issue(s):")
        for iss in issues:
            print(f"  ⚠ {iss}")
    else:
        print("[POST-PROCESSOR] Validation passed — report is clean.")

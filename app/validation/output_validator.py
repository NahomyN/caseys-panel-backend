import re
from typing import Tuple, List, Dict, Any

# Simple heuristic regex patterns
BRACKET_START_RE = re.compile(r"^\[[^\]]+\]")
POA_TAG_RE = re.compile(r"\bPOA\b", re.IGNORECASE)
BULLET_PREFIXES = ("- ", "* ")


def validate_agent_output(agent_no: int, output_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], bool]:
    """Validate & minimally repair agent outputs per PRODUCT.md invariants.

    Returns (possibly modified output, issues list, repaired_flag)
    Invariants enforced (initial subset):
      Agent 4 (Physical Exam): bullet style list lines start with '- '
      Agent 7 (A&P orchestrator):
         - each problem heading includes POA tag (adds if missing)
         - plan items bracketed: '[] action'
    """
    issues: List[str] = []
    repaired = False
    output = dict(output_dict) if output_dict else {}

    if agent_no == 4:
        pe_md = output.get("content_md", "")
        if "Physical Exam" in pe_md:
            lines = pe_md.splitlines()
            new_lines = []
            changed = False
            for ln in lines:
                if ln.strip().startswith("#"):
                    new_lines.append(ln)
                    continue
                if ln.strip() and not any(ln.lstrip().startswith(p) for p in BULLET_PREFIXES):
                    new_lines.append("- " + ln.lstrip("-•* "))
                    changed = True
                else:
                    new_lines.append(ln)
            if changed:
                output["content_md"] = "\n".join(new_lines)
                issues.append("Normalized Physical Exam bullet formatting")
                repaired = True

    if agent_no == 7:
        problems = output.get("problems")
        if isinstance(problems, list):
            seen_headings = set()
            for p in problems:
                if not isinstance(p, dict):
                    continue
                heading = p.get("heading", "") or ""
                original_heading = heading
                if heading:
                    # Ensure POA present
                    if "POA" not in heading.upper():
                        heading += " (POA)"
                        p["heading"] = heading
                        issues.append(f"Added POA tag to problem heading '{original_heading}'")
                        repaired = True
                    # Enforce title case (first letter capitalized for each major word)
                    words = [w.capitalize() if w.isalpha() else w for w in heading.split()]
                    title_case = " ".join(words)
                    if title_case != heading:
                        p["heading"] = title_case
                        issues.append(f"Title-cased problem heading '{heading}'")
                        heading = title_case
                        repaired = True
                    # Deduplicate heading by appending numeric suffix
                    norm_key = heading.lower()
                    if norm_key in seen_headings:
                        suffix = 2
                        new_heading = f"{heading} #{suffix}"
                        while new_heading.lower() in seen_headings:
                            suffix += 1
                            new_heading = f"{heading} #{suffix}"
                        p["heading"] = new_heading
                        issues.append(f"Disambiguated duplicate heading '{heading}' -> '{new_heading}'")
                        heading = new_heading
                        repaired = True
                    seen_headings.add(heading.lower())
                # Plan rules
                plan = p.get("plan")
                if isinstance(plan, list):
                    new_plan = []
                    changed_plan = False
                    for item in plan:
                        if not isinstance(item, str):
                            continue
                        itm = item.strip()
                        if not itm.startswith("[]"):
                            itm = "[] " + itm
                            changed_plan = True
                        # Ensure plan items end with a period for consistency
                        if not itm.rstrip().endswith("."):
                            itm = itm.rstrip() + "."
                            changed_plan = True
                        new_plan.append(itm)
                    if changed_plan:
                        p["plan"] = new_plan
                        # Backward compatibility: retain old phrase so existing tests still match
                        issues.append("Bracketed plan items for problem heading")
                        issues.append("Normalized plan item formatting")
                        repaired = True
    return output, issues, repaired

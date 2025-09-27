"""
Output validation and normalization service.
Ensures agent outputs conform to PRODUCT.md specifications.
"""
import re
from typing import Dict, Any, List, Tuple


def normalize_agent_4_output(content_md: str) -> str:
    """
    Normalize Agent 4 (PE) output to bullet format.
    PRODUCT.md spec: bullet-style PE with vitals; no fluff norms.
    """
    if not content_md.strip():
        return "# Physical Exam\n- No physical exam documented"
    
    lines = content_md.split('\n')
    normalized_lines = []
    in_pe_section = False
    
    for line in lines:
        stripped = line.strip()
        
        # Preserve headers
        if stripped.startswith('#'):
            normalized_lines.append(line)
            if 'physical' in stripped.lower() or 'exam' in stripped.lower():
                in_pe_section = True
            continue
        
        # Skip empty lines
        if not stripped:
            normalized_lines.append(line)
            continue
        
        # In PE section, ensure bullet format
        if in_pe_section and stripped:
            # If not already a bullet or sub-bullet, make it one
            if not stripped.startswith('-') and not stripped.startswith('  -'):
                # Check if it looks like a system header (HEENT:, CV:, etc.)
                if ':' in stripped and len(stripped.split(':')[0]) <= 10:
                    normalized_lines.append(f"- {stripped}")
                else:
                    # Regular finding, make it a bullet
                    normalized_lines.append(f"- {stripped}")
            else:
                # Already proper format
                normalized_lines.append(line)
        else:
            normalized_lines.append(line)
    
    return '\n'.join(normalized_lines)


def normalize_agent_7_output(content_md: str) -> str:
    """
    Normalize Agent 7 (A&P) output per PRODUCT.md specs:
    - Start with one-liner
    - Problem headings should be precise/billable
    - Plans in [] brackets, no numbering
    - Add POA tags where appropriate
    """
    if not content_md.strip():
        return "# Assessment & Plan\nNo assessment documented"
    
    lines = content_md.split('\n')
    normalized_lines = []
    has_oneliner = False
    in_ap_section = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Track if we're in A&P section
        if stripped.startswith('#') and ('assessment' in stripped.lower() or 'plan' in stripped.lower()):
            in_ap_section = True
            normalized_lines.append(line)
            i += 1
            continue
        
        # After A&P header, ensure one-liner exists
        if in_ap_section and not has_oneliner and stripped:
            if not stripped.startswith('##'):  # Not a problem heading
                has_oneliner = True
                # Ensure it's a proper one-liner (age + gender + chief complaint)
                if not re.match(r'^\d+[MF]?\s+(male|female|with|presenting)', stripped, re.IGNORECASE):
                    # Try to enhance it to proper one-liner format
                    if 'with' not in stripped.lower() and len(stripped.split()) < 8:
                        # Short line, likely not a proper one-liner, add generic one
                        normalized_lines.append("Patient with clinical presentation requiring assessment")
                        normalized_lines.append("")  # Add blank line
                        normalized_lines.append(line)  # Add the original line as problem section
                        i += 1
                        continue
                # Accept current line as one-liner
                normalized_lines.append(line)
            else:
                # This is a problem heading but we haven't seen a one-liner yet
                # Insert a generic one-liner
                normalized_lines.append("Patient with clinical presentation requiring assessment")
                normalized_lines.append("")  # Add blank line
                normalized_lines.append(line)  # Add the problem heading
                has_oneliner = True
            i += 1
            continue
        
        # Convert numbered plans to bracket format
        if in_ap_section and re.match(r'^\s*\d+\.?\s+', stripped):
            # Remove number and add brackets
            plan_text = re.sub(r'^\s*\d+\.?\s+', '', stripped)
            if not plan_text.startswith('['):
                plan_text = f"[{plan_text}]"
            normalized_lines.append(f"  {plan_text}")  # Indent plan items
            i += 1
            continue
        
        # Handle problem headings - ensure they're billable/precise
        if stripped.startswith('##'):
            # Basic cleanup - remove extra spaces, ensure proper case
            problem_heading = stripped.replace('##', '').strip()
            # Add POA tag for chronic conditions if not present
            if any(chronic in problem_heading.lower() for chronic in ['diabetes', 'hypertension', 'copd', 'cad']):
                if '(POA)' not in problem_heading and 'acute' not in problem_heading.lower():
                    problem_heading += " (POA)"
            normalized_lines.append(f"## {problem_heading}")
            i += 1
            continue
        
        # Regular lines
        normalized_lines.append(line)
        i += 1
    
    return '\n'.join(normalized_lines)


def validate_problem_plan_format(problem: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate individual problem-plan structure.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    
    if 'heading' not in problem:
        errors.append("Problem missing 'heading' field")
    
    if 'plan' not in problem:
        errors.append("Problem missing 'plan' field")
        return False, errors
    
    plan_items = problem['plan']
    if not isinstance(plan_items, list):
        errors.append("Plan must be a list of items")
        return False, errors
    
    # Check each plan item is in bracket format
    for i, item in enumerate(plan_items):
        if not isinstance(item, str):
            errors.append(f"Plan item {i} must be a string")
            continue
        
        # Should be in [action] format
        if not (item.strip().startswith('[') and item.strip().endswith(']')):
            errors.append(f"Plan item '{item}' should be in [bracket] format")
    
    return len(errors) == 0, errors


def validate_pe_bullet_format(content_md: str) -> Tuple[bool, List[str]]:
    """
    Validate PE content follows bullet format.
    Returns (is_valid, list_of_errors).
    """
    errors = []
    lines = content_md.split('\n')
    in_pe_content = False
    
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Track when we're in PE content
        if stripped.startswith('#') and ('physical' in stripped.lower() or 'exam' in stripped.lower()):
            in_pe_content = True
            continue
        
        # Skip empty lines and sub-headers
        if not stripped or stripped.startswith('#'):
            continue
        
        # In PE content, check format
        if in_pe_content:
            # Should be bullet format or sub-bullet
            if not (stripped.startswith('-') or stripped.startswith('  -') or stripped.startswith('*')):
                # Allow vitals line or system headers with colons
                if ':' not in stripped or len(stripped.split(':')[0]) > 15:
                    errors.append(f"Line {line_num}: '{stripped}' should be in bullet format")
    
    return len(errors) == 0, errors


def normalize_medication_list(med_list: List[str]) -> List[str]:
    """
    Normalize medication list format for consistency.
    """
    normalized = []
    for med in med_list:
        if not isinstance(med, str):
            continue
        
        # Basic cleanup
        med = med.strip()
        if not med:
            continue
        
        # Ensure proper case for common medications
        med_lower = med.lower()
        common_meds = {
            'lisinopril': 'Lisinopril',
            'metformin': 'Metformin', 
            'atorvastatin': 'Atorvastatin',
            'aspirin': 'Aspirin',
            'warfarin': 'Warfarin'
        }
        
        for generic, proper in common_meds.items():
            if med_lower.startswith(generic):
                med = med_lower.replace(generic, proper, 1)
                break
        
        normalized.append(med)
    
    return normalized


def clean_whitespace_content(content: str) -> str:
    """
    Clean excessive whitespace while preserving structure.
    """
    if not content:
        return ""
    
    # Split into lines and process
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Keep leading space for indentation but clean trailing
        if line.strip():  # Non-empty line
            # Preserve indentation, clean trailing spaces
            leading_spaces = len(line) - len(line.lstrip())
            cleaned_content = line.strip()
            cleaned_lines.append(' ' * leading_spaces + cleaned_content)
        else:
            # Empty line
            cleaned_lines.append('')
    
    # Remove excessive blank lines (more than 2 consecutive)
    final_lines = []
    blank_count = 0
    
    for line in cleaned_lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 2:  # Allow up to 2 consecutive blank lines
                final_lines.append(line)
        else:
            blank_count = 0
            final_lines.append(line)
    
    return '\n'.join(final_lines)

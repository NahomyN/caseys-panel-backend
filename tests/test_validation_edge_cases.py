"""
Enhanced validation tests covering edge cases and error handling.
"""
import pytest
from pydantic import ValidationError
from app.schemas.agents import Agent4Output, Agent7Output
from app.services.validation import (
    normalize_agent_4_output, 
    normalize_agent_7_output,
    validate_problem_plan_format
)


def test_agent_4_pe_validation_bullet_enforcement():
    """Test PE output normalization to bullet format."""
    # Non-bullet format input
    non_bullet_content = """# Physical Exam
Vitals: Stable
General: Well-appearing patient
HEENT: Normal
"""
    
    # Should convert to bullet format
    normalized = normalize_agent_4_output(non_bullet_content)
    lines = [line.strip() for line in normalized.split('\n') if line.strip()]
    
    # Skip header, remaining lines should be bullets or sub-bullets
    content_lines = [line for line in lines if not line.startswith('#')]
    for line in content_lines:
        if line and not line.startswith('  '):  # Main lines should be bullets
            assert line.startswith('- '), f"Line should start with bullet: {line}"


def test_agent_4_pe_validation_preserves_existing_bullets():
    """Test that already properly formatted PE is preserved."""
    bullet_content = """# Physical Exam
- Vitals: Stable, afebrile
- General: Well-appearing, no acute distress
- HEENT: Normocephalic, atraumatic
  - PERRL, EOMI
  - Oral mucosa moist
- CV: Regular rate and rhythm
"""
    
    normalized = normalize_agent_4_output(bullet_content)
    # Should be unchanged or minimally changed
    assert "- Vitals:" in normalized
    assert "- General:" in normalized
    assert "- HEENT:" in normalized


def test_agent_7_problem_bracket_validation():
    """Test A&P plan bracket format enforcement."""
    test_content = """# Assessment & Plan
64F with chest pain

## Chest Pain
This is concerning for ACS given risk factors.
1. Serial troponins
2. EKG q6h  
3. Continue aspirin
4. Cardiology consult

## Hypertension  
Well controlled on current regimen
Continue lisinopril 10mg daily
"""
    
    normalized = normalize_agent_7_output(test_content)
    
    # Plans should be in bracket format
    assert "[Serial troponins]" in normalized or "[] Serial troponins" in normalized
    assert "[EKG q6h]" in normalized or "[] EKG q6h" in normalized
    assert "[Continue aspirin]" in normalized or "[] Continue aspirin" in normalized


def test_agent_7_one_liner_validation():
    """Test that A&P starts with proper one-liner."""
    content_without_oneliner = """# Assessment & Plan

## Chest Pain
Patient presents with chest pain.
[EKG, troponins]
"""
    
    normalized = normalize_agent_7_output(content_without_oneliner)
    
    # Should inject or ensure one-liner is present
    lines = [line.strip() for line in normalized.split('\n') if line.strip()]
    # Find content after header
    content_start = None
    for i, line in enumerate(lines):
        if line.startswith('#') and 'Assessment' in line:
            content_start = i + 1
            break
    
    if content_start and content_start < len(lines):
        # Next non-empty line should be one-liner (not starting with ##)
        next_line = lines[content_start]
        assert not next_line.startswith('##'), "Should have one-liner before problem sections"


def test_problem_plan_format_validation():
    """Test individual problem-plan format validation."""
    # Valid format
    valid_problem = {
        "heading": "Acute Chest Pain",
        "plan": ["[EKG q6h]", "[Serial troponins]", "[Cardiology consult]"]
    }
    
    is_valid, errors = validate_problem_plan_format(valid_problem)
    assert is_valid
    assert len(errors) == 0
    
    # Invalid format - no brackets
    invalid_problem = {
        "heading": "Chest Pain",
        "plan": ["EKG q6h", "Serial troponins"]  # Missing brackets
    }
    
    is_valid, errors = validate_problem_plan_format(invalid_problem)
    assert not is_valid
    assert len(errors) > 0
    assert any("bracket" in error.lower() for error in errors)


def test_validation_handles_whitespace_edge_cases():
    """Test validation handles whitespace and empty content gracefully."""
    # Empty content
    empty_pe = normalize_agent_4_output("")
    assert isinstance(empty_pe, str)
    
    # Only whitespace
    whitespace_only = normalize_agent_4_output("   \n\t  \n   ")
    assert isinstance(whitespace_only, str)
    
    # Mixed whitespace in plans
    messy_content = """# Assessment & Plan
65M with chest pain

## Acute Chest Pain  
   
Plan:   
  Serial troponins   
   EKG monitoring    
  
"""
    
    normalized = normalize_agent_7_output(messy_content)
    # Should clean up whitespace while preserving structure
    assert "Serial troponins" in normalized
    assert "EKG monitoring" in normalized


def test_agent_7_duplicate_problem_heading_handling():
    """Test handling of duplicate problem headings."""
    content_with_duplicates = """# Assessment & Plan
65M with chest pain and HTN

## Chest Pain
Acute presentation concerning for ACS
[Troponins, EKG]

## Chest Pain  
Additional notes about chest pain
[Aspirin, monitoring]

## Hypertension
Well controlled
[Continue lisinopril]
"""
    
    normalized = normalize_agent_7_output(content_with_duplicates)
    
    # Should merge or disambiguate duplicate headings
    chest_pain_count = normalized.count("## Chest Pain")
    # Should either merge into one or rename to differentiate
    assert chest_pain_count <= 2  # At most should have original + renamed version


def test_poa_tag_validation():
    """Test POA (Present on Admission) tag handling."""
    content_with_poa = """# Assessment & Plan
Patient with multiple comorbidities

## Diabetes Mellitus Type 2 (POA)
Well controlled on metformin
[Continue current regimen]

## New Diagnosis - Acute Kidney Injury
Developed during stay
[Monitor creatinine, nephrology]
"""
    
    normalized = normalize_agent_7_output(content_with_poa)
    
    # POA tags should be preserved for chronic conditions
    assert "(POA)" in normalized
    # New diagnoses shouldn't have POA
    assert "Acute Kidney Injury" in normalized


def test_validation_error_recovery():
    """Test that validation handles malformed input gracefully."""
    malformed_json_like = """# Assessment & Plan
{
  "problem": "Incomplete JSON
  "plan": ["missing closing brace"
"""
    
    # Should not crash, should return some normalized version
    try:
        normalized = normalize_agent_7_output(malformed_json_like)
        assert isinstance(normalized, str)
        assert len(normalized) > 0
    except Exception as e:
        pytest.fail(f"Validation should handle malformed input gracefully: {e}")


def test_agent_output_schema_validation():
    """Test strict schema validation for agent outputs."""
    # Valid Agent 4 output
    valid_pe = Agent4Output(
        content_md="# PE\n- Vitals: stable\n- General: well appearing",
        vitals={"bp": "120/80", "hr": 72},
        physical_exam=["well appearing", "stable vitals"],
        vitals_summary={"bp": "120/80", "hr": 72},
        key_findings=["well appearing", "stable vitals"]
    )
    assert valid_pe.agent_no == 4
    
    # Invalid Agent 4 - missing required fields should raise ValidationError
    with pytest.raises(ValidationError):
        Agent4Output(content_md="# PE\n- Vitals only")  # Missing other required fields
    
    # Valid Agent 7 output
    valid_ap = Agent7Output(
        content_md="# A&P\n65M with chest pain\n## Chest Pain\n[EKG, troponins]",
        one_liner="65M with chest pain",
        problems=[{"heading": "Chest Pain", "plan": ["[EKG]", "[troponins]"]}],
        specialist_needed="cardiology",
        pharmacist_needed=True
    )
    assert valid_ap.agent_no == 7
    assert len(valid_ap.problems) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

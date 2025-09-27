from app.validation.output_validator import validate_agent_output


def test_agent4_physical_exam_bullets_normalized():
    raw_output = {
        "content_md": "# Physical Exam\n\nVS: BP 120/70 HR 70\nGeneral: NAD\n- Already bullet\n"  # one line missing bullet, one already bullet
    }
    updated, issues, repaired = validate_agent_output(4, raw_output)
    assert repaired is True
    assert any("Physical Exam bullet" in i for i in issues)
    lines = updated["content_md"].splitlines()
    # All non-heading, non-empty lines should start with '-' now
    pe_lines = [l for l in lines if l and not l.startswith("# ")]
    assert all(l.lstrip().startswith("- ") for l in pe_lines)


def test_agent7_problems_poa_and_plan_brackets_and_periods():
    raw_output = {
        "problems": [
            {"heading": "hypertension", "plan": ["Continue lisinopril", "Monitor BP"]},
            {"heading": "hypertension", "plan": ["Add lifestyle changes"]},  # duplicate heading triggers disambiguation
            {"heading": "Chest Pain - rule out acs", "plan": ["Serial troponins", "EKG monitor"]},
        ]
    }
    updated, issues, repaired = validate_agent_output(7, raw_output)
    assert repaired is True
    # POA tag added
    assert all("(POA)" in p["heading"] for p in updated["problems"])
    # Duplicate disambiguated (#2 suffix or similar)
    headings = [p["heading"] for p in updated["problems"]]
    assert len(set(headings)) == len(headings)
    # Plans bracketed and period terminated
    for p in updated["problems"]:
        for item in p.get("plan", []):
            assert item.startswith("[] ")
            assert item.rstrip().endswith(".")
    # Issues list should report bracket normalization or POA additions
    assert any("POA" in i for i in issues)
    assert any("Bracketed plan" in i for i in issues)


def test_agent7_no_change_returns_same_when_already_compliant():
    compliant = {
        "problems": [
            {"heading": "Hypertension (POA)", "plan": ["[] Continue lisinopril."]},
        ]
    }
    updated, issues, repaired = validate_agent_output(7, compliant)
    assert repaired is False
    assert updated == compliant
    assert issues == []

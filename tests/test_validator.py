from app.validation.output_validator import validate_agent_output


def test_validate_agent7_repairs_plan_and_poa():
    raw = {
        "problems": [
            {"heading": "Chest pain - rule out ACS", "plan": ["Serial troponins", "EKG monitoring"]},
            {"heading": "Hypertension", "plan": ["Continue lisinopril"]}
        ]
    }
    fixed, issues, repaired = validate_agent_output(7, raw)
    assert repaired is True
    assert any("POA" in p["heading"].upper() for p in fixed["problems"])  # at least one POA added
    for p in fixed["problems"]:
        for item in p["plan"]:
            assert item.startswith("[] ")
    assert any("Bracketed plan items" in i for i in issues)


def test_validate_agent4_bullets():
    raw_md = "# Physical Exam\nVS: stable\nGeneral: NAD"
    fixed, issues, repaired = validate_agent_output(4, {"content_md": raw_md})
    assert repaired is True
    assert "- VS: stable" in fixed["content_md"]
    assert any("Physical Exam" in i for i in issues)

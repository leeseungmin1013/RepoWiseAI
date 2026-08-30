from app.learning.roadmap_proposals import build_roadmap_diff, verify_roadmap_selection


def candidate(
    candidate_id: str,
    *,
    module_type: str,
    required: bool = False,
    prerequisites: list[str] | None = None,
    minutes: int = 4,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "module_type": module_type,
        "title": candidate_id,
        "path": f"src/{candidate_id}.py",
        "evidence_ids": [f"evidence:{candidate_id}"],
        "concept_ids": [],
        "estimated_minutes": minutes,
        "required": required,
        "prerequisite_ids": prerequisites or [],
        "reason": "verified evidence",
    }


def test_verifier_accepts_covered_evidenced_prerequisite_order():
    rows = [
        candidate("entry", module_type="orientation", required=True),
        candidate(
            "feature",
            module_type="feature_flow",
            required=True,
            prerequisites=["entry"],
        ),
    ]

    result = verify_roadmap_selection(rows, ["entry", "feature"], max_lessons=6)

    assert result["valid"] is True
    assert result["errors"] == []


def test_verifier_rejects_unknown_missing_coverage_and_bad_prerequisite_order():
    rows = [
        candidate("entry", module_type="orientation", required=True),
        candidate(
            "feature",
            module_type="feature_flow",
            required=True,
            prerequisites=["entry"],
        ),
    ]

    result = verify_roadmap_selection(rows, ["feature", "unknown"], max_lessons=6)

    assert result["valid"] is False
    assert any("unknown candidate IDs" in error for error in result["errors"])
    assert any("required coverage missing" in error for error in result["errors"])
    assert any("prerequisite order invalid" in error for error in result["errors"])


def test_diff_reports_add_remove_reorder_and_minutes():
    current = [
        {
            "candidate_id": "entry",
            "title": "entry",
            "module_type": "orientation",
            "estimated_minutes": 3,
        },
        {
            "candidate_id": "old",
            "title": "old",
            "module_type": "feature_flow",
            "estimated_minutes": 5,
        },
    ]
    proposed = [
        candidate("entry", module_type="orientation", minutes=3),
        candidate("new", module_type="feature_flow", minutes=7),
    ]

    diff = build_roadmap_diff(current, proposed, ["new", "entry"])

    assert [item["candidate_id"] for item in diff["added_lessons"]] == ["new"]
    assert [item["candidate_id"] for item in diff["removed_lessons"]] == ["old"]
    assert diff["order_changed"] is False
    assert diff["estimated_minutes_delta"] == 2
    assert diff["proposed_order"] == ["new", "entry"]

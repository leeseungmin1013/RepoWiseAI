from app.workers.repository_analysis import _reserve_chunk_template


def test_chunk_template_reservation_deduplicates_identical_files_without_autoflush() -> None:
    known_hashes = {"sha256:existing"}

    assert _reserve_chunk_template("sha256:empty", known_hashes) is True
    assert _reserve_chunk_template("sha256:empty", known_hashes) is False
    assert _reserve_chunk_template("sha256:existing", known_hashes) is False
    assert known_hashes == {"sha256:existing", "sha256:empty"}
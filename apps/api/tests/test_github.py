import pytest

from app.services.github import parse_github_url


def test_parse_public_github_repository_url() -> None:
    owner, name, canonical = parse_github_url("https://github.com/openai/openai-python.git")

    assert owner == "openai"
    assert name == "openai-python"
    assert canonical == "https://github.com/openai/openai-python"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/openai/openai-python",
        "https://gitlab.com/openai/openai-python",
        "https://github.com/openai/openai-python/tree/main",
    ],
)
def test_rejects_non_repository_urls(url: str) -> None:
    with pytest.raises(ValueError):
        parse_github_url(url)

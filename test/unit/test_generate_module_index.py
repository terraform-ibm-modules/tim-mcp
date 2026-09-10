"""
Tests for the generate_module_index.py script.
"""

import json

# Import the script functions directly
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.generate_module_index import (
    CATEGORY_KEYWORDS,
    categorize_module,
    clean_excerpt,
    fetch_submodule_description,
    generate_module_index,
    is_module_maintained,
    process_module,
)


class TestHelperFunctions:
    """Tests for the helper functions in generate_module_index.py."""

    def test_categorize_module_basic(self):
        """Test basic categorization functionality."""
        # Test that a module with a keyword in its name is categorized correctly
        for category, keywords in CATEGORY_KEYWORDS.items():
            if keywords:  # Make sure we have at least one keyword
                keyword = keywords[0]
                assert (
                    categorize_module(f"{keyword}-module", "Generic description")
                    == category
                )
                assert (
                    categorize_module("module", f"Description with {keyword}")
                    == category
                )

    def test_categorize_module_empty(self):
        """Test categorizing empty inputs."""
        assert categorize_module("", "") == "other"
        assert categorize_module(None, None) == "other"

    def test_categorize_module_priority(self):
        """Test that categories are checked in order (more specific first)."""
        # Create a test case with keywords from multiple categories
        # Get a keyword from the first category and one from a later category
        categories = list(CATEGORY_KEYWORDS.keys())
        if len(categories) >= 2:
            first_category = categories[0]
            second_category = categories[1]

            if CATEGORY_KEYWORDS[first_category] and CATEGORY_KEYWORDS[second_category]:
                first_keyword = CATEGORY_KEYWORDS[first_category][0]
                second_keyword = CATEGORY_KEYWORDS[second_category][0]

                # This should match the first category because categories are checked in order
                test_name = f"{first_keyword}-{second_keyword}"
                assert (
                    categorize_module(test_name, "Test description") == first_category
                )

    def test_clean_excerpt_unicode_symbols(self):
        """Test cleaning unicode symbols from README excerpts."""
        text = "IBM Cloud® provides Terraform™ for infrastructure as code."
        expected = "IBM Cloud provides Terraform for infrastructure as code."
        assert clean_excerpt(text) == expected

    def test_clean_excerpt_whitespace(self):
        """Test normalizing whitespace in README excerpts."""
        text = "This is a\nmulti-line\n\ntext with   extra   spaces."
        expected = "This is a multi-line\n\ntext with extra spaces."
        assert clean_excerpt(text) == expected

    def test_clean_excerpt_empty(self):
        """Test cleaning empty excerpts."""
        assert clean_excerpt("") == ""
        assert clean_excerpt(None) is None

    def test_clean_excerpt_paragraph_breaks(self):
        """Test preserving paragraph breaks in README excerpts."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        expected = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        assert clean_excerpt(text) == expected

    def test_clean_excerpt_html_entities(self):
        """Test cleaning HTML entities from README excerpts."""
        text = "IBM Cloud&reg; with Terraform&trade; and Copyright&copy; notice."
        expected = "IBM Cloud with Terraform and Copyright notice."
        assert clean_excerpt(text) == expected


@pytest.fixture
def mock_cache():
    """Create a mock cache."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    return mock_cache


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    mock_config = MagicMock()
    mock_config.allowed_namespaces = ["terraform-ibm-modules"]
    return mock_config


@pytest.fixture
def mock_terraform_client():
    """Create a mock TerraformClient."""
    mock_client = MagicMock()

    # Mock list_all_modules method
    mock_modules = [
        {
            "id": "terraform-ibm-modules/vpc/ibm",
            "namespace": "terraform-ibm-modules",
            "name": "vpc",
            "provider": "ibm",
            "description": "Creates VPC resources on IBM Cloud",
            "source": "https://github.com/terraform-ibm-modules/terraform-ibm-vpc",
            "published_at": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
            "downloads": 5000,
        },
        {
            "id": "terraform-ibm-modules/cos/ibm",
            "namespace": "terraform-ibm-modules",
            "name": "cos",
            "provider": "ibm",
            "description": "Creates Cloud Object Storage resources",
            "source": "https://github.com/terraform-ibm-modules/terraform-ibm-cos",
            "published_at": (datetime.now(UTC) - timedelta(days=45)).isoformat(),
            "downloads": 3000,
        },
        {
            "id": "terraform-ibm-modules/watsonx/ibm",
            "namespace": "terraform-ibm-modules",
            "name": "watsonx",
            "provider": "ibm",
            "description": "Creates WatsonX AI resources",
            "source": "https://github.com/terraform-ibm-modules/terraform-ibm-watsonx",
            "published_at": (datetime.now(UTC) - timedelta(days=15)).isoformat(),
            "downloads": 2000,
        },
        {
            "id": "terraform-ibm-modules/old-module/ibm",
            "namespace": "terraform-ibm-modules",
            "name": "old-module",
            "provider": "ibm",
            "description": "Old module that should be filtered out",
            "source": "https://github.com/terraform-ibm-modules/terraform-ibm-old-module",
            "published_at": (datetime.now(UTC) - timedelta(days=120)).isoformat(),
            "downloads": 1000,
        },
    ]

    mock_client.list_all_modules = AsyncMock(return_value=mock_modules)

    # Mock get_module_versions: fetch_submodules asks for the latest stable
    # version before fetching details, regardless of which module it's for.
    mock_client.get_module_versions = AsyncMock(return_value=["1.0.0"])

    # Mock get_module_details method
    mock_module_details = {
        "terraform-ibm-modules/vpc/ibm": {
            "submodules": [
                {"path": "modules/subnet", "name": "subnet"},
                {"path": "modules/security-group", "name": "security-group"},
            ]
        },
        "terraform-ibm-modules/cos/ibm": {
            "submodules": [{"path": "modules/bucket", "name": "bucket"}]
        },
        "terraform-ibm-modules/watsonx/ibm": {"submodules": []},
    }

    async def mock_get_module_details(namespace, name, provider, version):
        module_id = f"{namespace}/{name}/{provider}"
        return mock_module_details.get(module_id, {"submodules": []})

    mock_client.get_module_details = AsyncMock(side_effect=mock_get_module_details)

    return mock_client


@pytest.fixture
def mock_github_client():
    """Create a mock GitHubClient."""
    mock_client = MagicMock()

    # Mock parse_github_url method
    def mock_parse_github_url(source_url):
        if "terraform-ibm-vpc" in source_url:
            return "terraform-ibm-modules", "terraform-ibm-vpc"
        elif "terraform-ibm-cos" in source_url:
            return "terraform-ibm-modules", "terraform-ibm-cos"
        elif "terraform-ibm-watsonx" in source_url:
            return "terraform-ibm-modules", "terraform-ibm-watsonx"
        elif "terraform-ibm-old-module" in source_url:
            return "terraform-ibm-modules", "terraform-ibm-old-module"
        return None

    mock_client.parse_github_url = MagicMock(side_effect=mock_parse_github_url)

    # Mock get_repository_info: every repo is core-team and unarchived except
    # old-module, which lacks the required topic -- with the age filter gone,
    # that (not its age) is what excludes it now.
    mock_repo_info = {
        "terraform-ibm-vpc": {"archived": False, "topics": ["core-team"]},
        "terraform-ibm-cos": {"archived": False, "topics": ["core-team"]},
        "terraform-ibm-watsonx": {"archived": False, "topics": ["core-team"]},
        "terraform-ibm-old-module": {"archived": False, "topics": ["community"]},
    }

    async def mock_get_repository_info(owner, repo):
        return mock_repo_info.get(repo, {"archived": False, "topics": []})

    mock_client.get_repository_info = AsyncMock(side_effect=mock_get_repository_info)

    # Mock get_file_content method
    mock_readme_contents = {
        ("terraform-ibm-modules", "terraform-ibm-vpc"): {
            "decoded_content": "# IBM VPC Module\n\nThis module creates VPC resources on IBM Cloud.\n\n## Features\n\n- Creates VPC\n- Creates subnets\n- Creates security groups\n\n## Prerequisites\n\nYou need permissions to create VPC resources."
        },
        ("terraform-ibm-modules", "terraform-ibm-cos"): {
            "decoded_content": "# IBM Cloud Object Storage Module\n\nThis module creates Cloud Object Storage resources.\n\n## Summary\n\nProvides a Cloud Object Storage instance with buckets and access policies.\n\n## Requirements\n\n- IBM Cloud account\n- Terraform installed"
        },
        ("terraform-ibm-modules", "terraform-ibm-watsonx"): {
            "decoded_content": "# IBM WatsonX Module\n\nThis module creates WatsonX AI resources on IBM Cloud.\n\n## Features\n\n- Creates WatsonX instances\n- Configures AI models\n- Sets up training data\n\n## Usage\n\nSee examples directory."
        },
    }

    async def mock_get_file_content(owner, repo, path):
        if path == "README.md":
            return mock_readme_contents.get((owner, repo), {"decoded_content": ""})
        return {"decoded_content": ""}

    mock_client.get_file_content = AsyncMock(side_effect=mock_get_file_content)

    return mock_client


def _as_async_context_manager(mock_obj):
    """Wrap a mock client so ``async with ClientClass(...) as x`` yields it."""
    cm = MagicMock(return_value=mock_obj)
    mock_obj.__aenter__ = AsyncMock(return_value=mock_obj)
    mock_obj.__aexit__ = AsyncMock(return_value=None)
    return cm


@pytest.mark.asyncio
async def test_generate_module_index(
    mock_config, mock_cache, mock_terraform_client, mock_github_client, tmp_path
):
    """
    Test the real generate_module_index function end to end.

    This used to run against a local reimplementation that duplicated (and
    drifted from) the actual filtering logic -- it still applied the old
    90-day age filter after that filter was removed from the real code, so
    it kept passing regardless of whether generate_module_index was correct.
    Runs the real function now, with load_config/TerraformClient/GitHubClient
    patched the way the integration test patches them.
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    output_path = static_dir / "module_index.json"

    with (
        patch("scripts.generate_module_index.load_config", return_value=mock_config),
        patch(
            "scripts.generate_module_index.TerraformClient",
            _as_async_context_manager(mock_terraform_client),
        ),
        patch(
            "scripts.generate_module_index.GitHubClient",
            _as_async_context_manager(mock_github_client),
        ),
    ):
        await generate_module_index(output_path=output_path)

    assert output_path.exists()

    with open(output_path) as f:
        output_data = json.load(f)

    # Verify the structure and content
    assert "generated_at" in output_data
    assert output_data["namespace"] == "terraform-ibm-modules"
    # old-module lacks the core-team topic -- see mock_github_client's
    # get_repository_info -- not filtered by age (that filter is gone).
    assert output_data["total_modules"] == 3

    # Verify modules are sorted by downloads
    modules = output_data["modules"]
    assert len(modules) == 3
    assert modules[0]["id"] == "terraform-ibm-modules/vpc/ibm"
    assert modules[1]["id"] == "terraform-ibm-modules/cos/ibm"
    assert modules[2]["id"] == "terraform-ibm-modules/watsonx/ibm"

    # Verify categories
    # We don't need to test specific category assignments as they might change
    # Just verify we have categories assigned
    assert "category" in modules[0]
    assert "category" in modules[1]
    assert "category" in modules[2]

    # Verify submodules
    assert len(modules[0]["submodules"]) == 2
    assert modules[0]["submodules"][0]["name"] == "security-group"  # Should be sorted
    assert modules[0]["submodules"][1]["name"] == "subnet"

    # Verify README excerpts
    assert "VPC resources" in modules[0]["readme_excerpt"]
    assert "Cloud Object Storage" in modules[1]["readme_excerpt"]
    assert "WatsonX AI resources" in modules[2]["readme_excerpt"]


@pytest.mark.asyncio
async def test_generate_module_index_with_exceptions(
    mock_config, mock_cache, mock_terraform_client, mock_github_client, tmp_path
):
    """Test the real generate_module_index function when per-module fetches fail."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()

    # Make the GitHub client raise an exception for one of the modules
    async def mock_get_file_content_with_exception(owner, repo, path):
        if repo == "terraform-ibm-cos":
            raise Exception("Failed to fetch README")

        if path == "README.md":
            return {"decoded_content": f"# {repo}\n\nThis is a test module for {repo}."}
        return {"decoded_content": ""}

    mock_github_client.get_file_content = AsyncMock(
        side_effect=mock_get_file_content_with_exception
    )

    # Make the Terraform client raise an exception for one of the module details
    async def mock_get_module_details_with_exception(
        namespace, name, provider, version
    ):
        if name == "watsonx":
            raise Exception("Failed to fetch module details")

        module_id = f"{namespace}/{name}/{provider}"
        if module_id == "terraform-ibm-modules/vpc/ibm":
            return {
                "submodules": [
                    {"path": "modules/subnet", "name": "subnet"},
                    {"path": "modules/security-group", "name": "security-group"},
                ]
            }
        return {"submodules": []}

    mock_terraform_client.get_module_details = AsyncMock(
        side_effect=mock_get_module_details_with_exception
    )

    output_path = static_dir / "module_index.json"

    with (
        patch("scripts.generate_module_index.load_config", return_value=mock_config),
        patch(
            "scripts.generate_module_index.TerraformClient",
            _as_async_context_manager(mock_terraform_client),
        ),
        patch(
            "scripts.generate_module_index.GitHubClient",
            _as_async_context_manager(mock_github_client),
        ),
    ):
        await generate_module_index(output_path=output_path)

    assert output_path.exists()

    with open(output_path) as f:
        output_data = json.load(f)

    # Verify the structure and content
    assert "generated_at" in output_data
    assert output_data["total_modules"] == 3  # Should still include all valid modules

    # Verify modules that had exceptions still have basic info but empty submodules/excerpts
    modules = output_data["modules"]
    cos_module = next(m for m in modules if m["id"] == "terraform-ibm-modules/cos/ibm")
    watsonx_module = next(
        m for m in modules if m["id"] == "terraform-ibm-modules/watsonx/ibm"
    )

    assert cos_module["readme_excerpt"] == ""  # README fetch failed
    assert watsonx_module["submodules"] == []  # Module details fetch failed


@pytest.mark.asyncio
async def test_generate_module_index_reports_unexpected_exceptions(
    mock_config, mock_cache, mock_terraform_client, mock_github_client, tmp_path, capsys
):
    """
    process_module runs inside asyncio.gather(..., return_exceptions=True), so
    an exception it doesn't itself catch becomes a plain result in the batch --
    it must be reported and the module dropped, not silently absorbed as if it
    had simply failed a filter. Forces a real exception (not a filtering
    decision) by making parse_github_url misbehave for one module.
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    output_path = static_dir / "module_index.json"

    real_parse = mock_github_client.parse_github_url

    def flaky_parse_github_url(source_url):
        if "terraform-ibm-cos" in source_url:
            raise RuntimeError("unexpected parsing bug")
        return real_parse(source_url)

    mock_github_client.parse_github_url = MagicMock(side_effect=flaky_parse_github_url)

    with (
        patch("scripts.generate_module_index.load_config", return_value=mock_config),
        patch(
            "scripts.generate_module_index.TerraformClient",
            _as_async_context_manager(mock_terraform_client),
        ),
        patch(
            "scripts.generate_module_index.GitHubClient",
            _as_async_context_manager(mock_github_client),
        ),
    ):
        await generate_module_index(output_path=output_path)

    with open(output_path) as f:
        output_data = json.load(f)

    ids = {m["id"] for m in output_data["modules"]}
    assert "terraform-ibm-modules/cos/ibm" not in ids
    # The other modules in the batch are unaffected by cos's failure.
    assert "terraform-ibm-modules/vpc/ibm" in ids

    # The failure is visible, not silently dropped.
    captured = capsys.readouterr()
    assert "terraform-ibm-modules/cos/ibm" in captured.out
    assert "RuntimeError" in captured.out
    assert "unexpected parsing bug" in captured.out


class TestSubmoduleDescription:
    """Tests for the fetch_submodule_description function."""

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_basic(self):
        """Test fetching a basic submodule description."""
        mock_gh_client = MagicMock()

        # Mock README content with a clear description
        readme_content = """# FSCloud Submodule

This is a comprehensive Financial Services Cloud compliant configuration.

It provides the following features:
- Encryption at rest
- BYOK support
- Activity tracking

## Usage

See the examples directory.
"""

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": readme_content}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-cos",
            "modules/fscloud",
        )

        assert result != ""
        assert "Financial Services Cloud" in result
        assert len(result) <= 1200  # Should respect character limit

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_with_bullet_list(self):
        """Test fetching description that ends with a colon and has a bullet list."""
        mock_gh_client = MagicMock()

        readme_content = """# Redis FSCloud Module

This submodule includes the following:
- IBM Cloud Framework for Financial Services support
- Context Based Restrictions (CBR) rules
- BYOK encryption with Key Protect
- Activity Tracker integration
- Security and Compliance Center integration

## Prerequisites

IBM Cloud account required.
"""

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": readme_content}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-redis",
            "modules/fscloud",
        )

        assert result != ""
        # Should include the bullet list items formatted inline
        assert "Financial Services" in result
        assert "Context Based Restrictions" in result
        assert "\n" not in result  # Should be normalized to single line
        assert len(result) <= 1200

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_truncation(self):
        """Test that very long descriptions are truncated at word boundaries."""
        mock_gh_client = MagicMock()

        # Create a very long paragraph
        long_text = "This is a test description. " * 100  # Will exceed 1200 chars
        readme_content = f"""# Long Module

{long_text}

## More content
"""

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": readme_content}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-test",
            "modules/test",
        )

        assert result != ""
        assert len(result) <= 1200
        # Should end at a word boundary, not mid-word
        assert not result.endswith(" ")  # No trailing space

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_no_readme(self):
        """Test handling when README doesn't exist."""
        mock_gh_client = MagicMock()

        # Mock a 404 error
        mock_gh_client.get_file_content = AsyncMock(
            side_effect=Exception("404 Not Found")
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-test",
            "modules/missing",
        )

        assert result == ""  # Should return empty string on error

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_empty_readme(self):
        """Test handling when README exists but is empty."""
        mock_gh_client = MagicMock()

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": ""}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-test",
            "modules/empty",
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_markdown_links_removed(self):
        """Test that markdown links are removed from descriptions."""
        mock_gh_client = MagicMock()

        readme_content = """# Module with Links

This module uses [IBM Cloud](https://cloud.ibm.com) and integrates with [Key Protect](https://cloud.ibm.com/catalog/services/key-protect).

See the [documentation](https://github.com/terraform-ibm-modules/terraform-ibm-cos) for details.
"""

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": readme_content}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-test",
            "modules/test",
        )

        assert result != ""
        # Links should be removed, only text remains
        assert "[" not in result
        assert "](" not in result
        assert "IBM Cloud" in result
        assert "Key Protect" in result

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_etc_suffix(self):
        """Test that bullet lists get properly extracted and formatted."""
        mock_gh_client = MagicMock()

        readme_content = """# Module with Many Features

This module includes the following:

- Feature 1
- Feature 2
- Feature 3
- Feature 4
- Feature 5
- Feature 6
- Feature 7

## More info
"""

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": readme_content}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-test",
            "modules/test",
        )

        assert result != ""
        # The implementation currently always adds "etc" suffix
        assert "etc" in result
        assert "Feature 1" in result
        # Should limit to first 5 items when there are more
        assert "Feature 5" in result or "Feature 6" in result

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_whitespace_normalization(self):
        """Test that multi-line text is normalized to single line."""
        mock_gh_client = MagicMock()

        readme_content = """# Module

This is a description
that spans multiple
lines and should be
normalized to a single line.

## More content
"""

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": readme_content}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-test",
            "modules/test",
        )

        assert result != ""
        # Newlines should be collapsed to spaces
        assert "\n" not in result
        assert "multiple lines" in result or "multiplelines" in result.replace(" ", "")

    @pytest.mark.asyncio
    async def test_fetch_submodule_description_skips_html_comments_in_fallback(self):
        """Test that HTML comments are skipped even in second pass fallback."""
        mock_gh_client = MagicMock()

        # Simulate README structure like vpc-private-path module:
        # Title, then multi-line HTML comment with text, then actual description
        readme_content = """# IBM Cloud Private Path module

<!--
Add a description of modules in this repo.
Expand on the repo short description in the .github/settings.yml file.

For information, see "Module names and descriptions" at
https://terraform-ibm-modules.github.io/documentation/#/implementation-guidelines?id=module-names-and-descriptions
-->

The Private Path solution solves security, privacy and complexity problems.

## More content
"""

        mock_gh_client.get_file_content = AsyncMock(
            return_value={"decoded_content": readme_content}
        )

        result = await fetch_submodule_description(
            mock_gh_client,
            "terraform-ibm-modules",
            "terraform-ibm-vpc-private-path",
            "modules/test",
        )

        assert result != ""
        # Should extract actual description, not HTML comment content
        assert "Private Path solution" in result
        assert "For information, see" not in result  # This was in HTML comment
        assert "module names and descriptions" not in result  # Also in HTML comment
        # Should not extract the header
        assert not result.startswith("# IBM Cloud Private Path")


class TestParallelProcessing:
    """Tests for parallel processing functionality."""

    @pytest.mark.asyncio
    async def test_parallel_submodule_fetching(self):
        """Test that submodules are fetched in parallel."""
        import asyncio

        mock_gh_client = MagicMock()
        call_times = []

        async def track_call_time(*args, **kwargs):
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)  # Simulate API call delay
            return {"decoded_content": "# Test\n\nDescription text."}

        mock_gh_client.get_file_content = AsyncMock(side_effect=track_call_time)

        # Simulate fetching 3 submodules
        submodules = [
            {"path": "modules/sub1"},
            {"path": "modules/sub2"},
            {"path": "modules/sub3"},
        ]

        tasks = [
            fetch_submodule_description(mock_gh_client, "owner", "repo", sub["path"])
            for sub in submodules
        ]

        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*tasks)
        total_time = asyncio.get_event_loop().time() - start_time

        # All should complete
        assert len(results) == 3
        assert all(r != "" for r in results)

        # Should take ~0.1s (parallel) not ~0.3s (sequential)
        # Add some buffer for test execution overhead
        assert total_time < 0.25, (
            f"Parallel execution took {total_time}s, expected < 0.25s"
        )

        # Verify calls were made in parallel (timestamps should be close)
        if len(call_times) >= 2:
            time_diff = max(call_times) - min(call_times)
            assert time_diff < 0.1, "Calls should start within 0.1s of each other"

    @pytest.mark.asyncio
    async def test_parallel_exception_handling(self):
        """Test that exceptions in parallel processing don't stop other tasks."""
        import asyncio

        mock_gh_client = MagicMock()

        call_count = 0

        async def fail_on_second_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Simulated API error")
            await asyncio.sleep(0.05)
            return {"decoded_content": "# Test\n\nDescription text."}

        mock_gh_client.get_file_content = AsyncMock(side_effect=fail_on_second_call)

        # Fetch 3 submodules, one will fail
        tasks = [
            fetch_submodule_description(
                mock_gh_client, "owner", "repo", f"modules/sub{i}"
            )
            for i in range(3)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Should have 3 results
        assert len(results) == 3

        # One should be empty (failed), others should succeed
        successful = [r for r in results if isinstance(r, str) and r != ""]
        assert len(successful) == 2

    @pytest.mark.asyncio
    async def test_batched_module_processing(self):
        """Test that modules are processed in batches."""
        # This is more of an integration test concept
        # The actual batching happens in generate_module_index
        # We can verify the batch size logic works

        # Simulate 25 modules processed in batches of 10
        total_modules = 25
        batch_size = 10

        batches = []
        for i in range(0, total_modules, batch_size):
            batch = list(range(i, min(i + batch_size, total_modules)))
            batches.append(batch)

        # Should have 3 batches: [0-9], [10-19], [20-24]
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 5

        # Verify all modules are included
        all_items = []
        for batch in batches:
            all_items.extend(batch)
        assert sorted(all_items) == list(range(total_modules))


class TestIsModuleMaintained:
    """
    Tests for is_module_maintained -- the check the index's own
    filter_criteria has always claimed to run (required_topics,
    exclude_archived) but never actually did until now.
    """

    @pytest.mark.asyncio
    async def test_unarchived_with_required_topic_is_maintained(self):
        gh = MagicMock()
        gh.parse_github_url = MagicMock(
            return_value=("terraform-ibm-modules", "terraform-ibm-x")
        )
        gh.get_repository_info = AsyncMock(
            return_value={
                "archived": False,
                "topics": ["core-team", "terraform-module"],
            }
        )
        assert (
            await is_module_maintained(
                gh,
                "terraform-ibm-modules/x/ibm",
                "https://github.com/terraform-ibm-modules/terraform-ibm-x",
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_archived_repo_is_excluded(self):
        """
        Archived excludes even when the required topic is present -- the
        topic alone isn't enough to keep a repo the org has retired.
        """
        gh = MagicMock()
        gh.parse_github_url = MagicMock(
            return_value=("terraform-ibm-modules", "terraform-ibm-x")
        )
        gh.get_repository_info = AsyncMock(
            return_value={"archived": True, "topics": ["core-team"]}
        )
        assert (
            await is_module_maintained(
                gh, "x", "https://github.com/terraform-ibm-modules/terraform-ibm-x"
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_missing_required_topic_is_excluded(self):
        """A repo without the core-team topic is excluded, however popular."""
        gh = MagicMock()
        gh.parse_github_url = MagicMock(
            return_value=("terraform-ibm-modules", "terraform-ibm-x")
        )
        gh.get_repository_info = AsyncMock(
            return_value={"archived": False, "topics": ["terraform-module"]}
        )
        assert (
            await is_module_maintained(
                gh, "x", "https://github.com/terraform-ibm-modules/terraform-ibm-x"
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_unparsable_url_is_excluded(self):
        gh = MagicMock()
        gh.parse_github_url = MagicMock(return_value=None)
        assert await is_module_maintained(gh, "x", "not-a-github-url") is False

    @pytest.mark.asyncio
    async def test_repository_lookup_failure_is_excluded_not_raised(self):
        """
        Defaults to excluding, matching search.py's _is_repository_valid --
        a module the check can't verify should not appear as verified.
        """
        gh = MagicMock()
        gh.parse_github_url = MagicMock(
            return_value=("terraform-ibm-modules", "terraform-ibm-x")
        )
        gh.get_repository_info = AsyncMock(side_effect=RuntimeError("rate limited"))
        assert (
            await is_module_maintained(
                gh, "x", "https://github.com/terraform-ibm-modules/terraform-ibm-x"
            )
            is False
        )


class TestProcessModuleFiltering:
    """
    process_module used to filter on Terraform Registry release recency
    (published_at, 90 days). That filter is gone: this org's dependency bot
    pushes to every repo regardless of real module activity, so neither
    release nor push recency can separate a maintained module from an
    abandoned one -- these tests lock in the replacement (topic + archived).
    """

    @staticmethod
    def _module(**overrides):
        base = {
            "id": "terraform-ibm-modules/resource-group/ibm/1.6.1",
            "namespace": "terraform-ibm-modules",
            "name": "resource-group",
            "provider": "ibm",
            "description": "Creates a resource group",
            "source": "https://github.com/terraform-ibm-modules/terraform-ibm-resource-group",
            "published_at": "2026-05-20T00:00:00Z",  # >90 days old at time of writing
            "downloads": 2_282_006,
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_stable_module_with_old_release_is_kept(self):
        """
        The motivating case: resource-group has 2.3M downloads and is
        actively maintained, but rarely needs a release. The old age filter
        dropped it; the topic-based check keeps it.
        """
        tf = MagicMock()
        gh = MagicMock()
        gh.parse_github_url = MagicMock(
            return_value=("terraform-ibm-modules", "terraform-ibm-resource-group")
        )
        gh.get_repository_info = AsyncMock(
            return_value={"archived": False, "topics": ["core-team"]}
        )
        gh.get_file_content = AsyncMock(return_value={"decoded_content": ""})
        tf.get_module_details = AsyncMock(return_value={"submodules": []})

        result = await process_module(self._module(), tf, gh)

        assert result is not None
        assert result["id"] == "terraform-ibm-modules/resource-group/ibm/1.6.1"

    @pytest.mark.asyncio
    async def test_wrong_org_is_still_excluded(self):
        tf, gh = MagicMock(), MagicMock()
        module = self._module(
            source="https://github.com/someone-else/terraform-ibm-resource-group"
        )

        result = await process_module(module, tf, gh)

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_topic_excludes_a_recently_released_module(self):
        """Being fresh by release date doesn't bypass the topic check."""
        tf = MagicMock()
        gh = MagicMock()
        gh.parse_github_url = MagicMock(
            return_value=("terraform-ibm-modules", "terraform-ibm-community-module")
        )
        gh.get_repository_info = AsyncMock(
            return_value={"archived": False, "topics": ["terraform-module"]}
        )

        module = self._module(
            id="terraform-ibm-modules/community-module/ibm/1.0.0",
            name="community-module",
            source="https://github.com/terraform-ibm-modules/terraform-ibm-community-module",
            published_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        result = await process_module(module, tf, gh)

        assert result is None

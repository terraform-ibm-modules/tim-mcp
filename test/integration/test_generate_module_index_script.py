"""
Integration test for the generate_module_index.py script.
See also the unit tests under test/unit/test_generate_module_index.py.
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from generate_module_index import generate_module_index


@pytest.mark.asyncio
async def test_generate_module_index_script_execution(tmp_path, monkeypatch):
    """
    Test that the generate_module_index script executes successfully.

    This integration test verifies:
    1. The script can be imported and called
    2. Cache is initialized correctly
    3. The script produces valid JSON output
    4. Basic data structure is correct
    """
    # Set up environment
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token-for-testing")

    # Create output directory
    output_file = tmp_path / "module_index.json"

    # Mock the config
    mock_config = MagicMock()
    mock_config.allowed_namespaces = ["terraform-ibm-modules"]

    # Mock the clients to avoid real API calls
    mock_tf_client = MagicMock()
    mock_tf_client.__aenter__ = AsyncMock(return_value=mock_tf_client)
    mock_tf_client.__aexit__ = AsyncMock(return_value=None)
    mock_tf_client.list_all_modules = AsyncMock(
        return_value=[
            {
                "id": "terraform-ibm-modules/test-module/ibm/1.0.0",
                "namespace": "terraform-ibm-modules",
                "name": "test-module",
                "provider": "ibm",
                "description": "Test module",
                "source": "https://github.com/terraform-ibm-modules/terraform-ibm-test-module",
                "published_at": "2026-01-01T00:00:00Z",
                "downloads": 100,
            }
        ]
    )

    mock_gh_client = MagicMock()
    mock_gh_client.__aenter__ = AsyncMock(return_value=mock_gh_client)
    mock_gh_client.__aexit__ = AsyncMock(return_value=None)
    mock_gh_client.parse_github_url = MagicMock(
        return_value=("terraform-ibm-modules", "terraform-ibm-test-module")
    )
    mock_gh_client.get_repository_info = AsyncMock(
        return_value={"archived": False, "topics": ["core-team", "terraform-module"]}
    )
    mock_gh_client.get_file_content = AsyncMock(return_value={"decoded_content": ""})

    # Patch the dependencies
    with patch("generate_module_index.load_config", return_value=mock_config):
        with patch(
            "generate_module_index.TerraformClient", return_value=mock_tf_client
        ):
            with patch(
                "generate_module_index.GitHubClient", return_value=mock_gh_client
            ):
                await generate_module_index(output_path=output_file)

    # Verify the output file was created
    assert output_file.exists(), "Output file should be created"

    # Verify it's valid JSON
    with open(output_file) as f:
        data = json.load(f)

    # Verify basic structure
    assert "generated_at" in data
    assert "total_modules" in data
    assert "modules" in data
    assert isinstance(data["modules"], list)

    # The one module the mocks describe must actually survive filtering --
    # asyncio.gather(..., return_exceptions=True) in generate_module_index
    # will otherwise swallow a mock/wiring mismatch as a silently-dropped
    # module rather than a failed test (this caught exactly that once).
    assert data["total_modules"] == 1
    assert data["modules"][0]["id"] == "terraform-ibm-modules/test-module/ibm/1.0.0"


@pytest.mark.asyncio
async def test_generate_module_index_excludes_repo_missing_required_topic(
    tmp_path, monkeypatch
):
    """A module whose repo lacks the required topic is filtered out."""
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token-for-testing")
    output_file = tmp_path / "module_index.json"

    mock_config = MagicMock()
    mock_config.allowed_namespaces = ["terraform-ibm-modules"]

    mock_tf_client = MagicMock()
    mock_tf_client.__aenter__ = AsyncMock(return_value=mock_tf_client)
    mock_tf_client.__aexit__ = AsyncMock(return_value=None)
    mock_tf_client.list_all_modules = AsyncMock(
        return_value=[
            {
                "id": "terraform-ibm-modules/community-module/ibm/1.0.0",
                "namespace": "terraform-ibm-modules",
                "name": "community-module",
                "provider": "ibm",
                "description": "Not a core-team module",
                "source": "https://github.com/terraform-ibm-modules/terraform-ibm-community-module",
                "published_at": "2026-01-01T00:00:00Z",
                "downloads": 100,
            }
        ]
    )

    mock_gh_client = MagicMock()
    mock_gh_client.__aenter__ = AsyncMock(return_value=mock_gh_client)
    mock_gh_client.__aexit__ = AsyncMock(return_value=None)
    mock_gh_client.parse_github_url = MagicMock(
        return_value=("terraform-ibm-modules", "terraform-ibm-community-module")
    )
    mock_gh_client.get_repository_info = AsyncMock(
        return_value={"archived": False, "topics": ["terraform-module"]}
    )

    with patch("generate_module_index.load_config", return_value=mock_config):
        with patch(
            "generate_module_index.TerraformClient", return_value=mock_tf_client
        ):
            with patch(
                "generate_module_index.GitHubClient", return_value=mock_gh_client
            ):
                await generate_module_index(output_path=output_file)

    with open(output_file) as f:
        data = json.load(f)

    assert data["total_modules"] == 0

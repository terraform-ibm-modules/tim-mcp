#!/usr/bin/env python3
"""
Test script to reproduce the parameter validation issue with include_files.
"""
import asyncio
import json
from tim_mcp.server import get_content


async def test_parameter_formats():
    """Test different parameter formats to see which ones work."""
    module_id = "terraform-ibm-modules/cos/ibm"
    path = "examples/basic"

    test_cases = [
        # Correct format - actual array
        {
            "name": "Proper array format",
            "include_files": [".*\\.tf$", ".*\\.md$"],
            "should_work": True
        },
        # Problematic format - JSON string
        {
            "name": "JSON string format (problematic)",
            "include_files": "[\".*\\\\.tf$\", \".*\\\\.md$\"]",
            "should_work": False
        },
        # None (should work)
        {
            "name": "None value",
            "include_files": None,
            "should_work": True
        }
    ]

    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        print(f"include_files value: {test_case['include_files']}")
        print(f"include_files type: {type(test_case['include_files'])}")

        try:
            result = await get_content(
                module_id=module_id,
                path=path,
                include_files=test_case["include_files"],
                exclude_files=None,
                include_readme=True,
                version="latest"
            )
            print("✅ SUCCESS - Parameter validation passed")
            if not test_case["should_work"]:
                print("⚠️  UNEXPECTED - This was expected to fail but didn't")

        except Exception as e:
            print(f"❌ FAILED - {type(e).__name__}: {e}")
            if test_case["should_work"]:
                print("⚠️  UNEXPECTED - This should have worked")


if __name__ == "__main__":
    asyncio.run(test_parameter_formats())
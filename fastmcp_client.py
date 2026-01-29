import asyncio
from fastmcp import Client

async def main():
    client = Client("http://127.0.0.1:8000/mcp")

    async with client:
        # Discover tools
        tools = await client.list_tools()
        print("Discovered tools:")
        for tool in tools:
            print(f"- {tool.name}")
            print(f"  {tool.description}")
        
        # Call the dependency suggestion tool
        result = await client.call_tool(
            "suggest_module_dependencies",
            {
                "module_path": "https://github.com/terraform-ibm-modules/terraform-ibm-key-protect",
                "ref": "mcp-mappings"
            },
        )

        print("\nSuggested dependency setup:")
        print(result)

if __name__ == "__main__":
    asyncio.run(main())

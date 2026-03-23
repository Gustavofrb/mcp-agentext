"""Teste automatizado do MCP server."""

import asyncio
from fastmcp import Client


def show(result):
    """Exibe o resultado de uma tool call."""
    print(f"  {result.data}")


async def main():
    client = Client("server.py")

    async with client:
        # Listar tools
        tools = await client.list_tools()
        print("=== TOOLS DISPONÍVEIS ===")
        for t in tools:
            print(f"  - {t.name}: {t.description}")
        print()

        # 1. Criar arquivo
        print("=== CREATE ===")
        show(await client.call_tool("create_file", {
            "file_path": "C:/TEMP/Central IT/Agentext/test/hello.txt",
            "content": "Olá FastMCP!"
        }))

        # 2. Ler arquivo
        print("=== READ ===")
        show(await client.call_tool("read_file", {
            "file_path": "C:/TEMP/Central IT/Agentext/test/hello.txt"
        }))

        # 3. Editar arquivo (substituição parcial)
        print("=== EDIT (parcial) ===")
        show(await client.call_tool("edit_file", {
            "file_path": "C:/TEMP/Central IT/Agentext/test/hello.txt",
            "old_text": "FastMCP",
            "new_text": "FastMCP Server"
        }))

        # 4. Ler de novo pra confirmar
        print("=== READ (após edit) ===")
        show(await client.call_tool("read_file", {
            "file_path": "C:/TEMP/Central IT/Agentext/test/hello.txt"
        }))

        # 5. Listar diretório
        print("=== LIST ===")
        show(await client.call_tool("list_files", {
            "dir_path": "C:/TEMP/Central IT/Agentext/test"
        }))

        # 6. Deletar
        print("=== DELETE ===")
        show(await client.call_tool("delete_file", {
            "file_path": "C:/TEMP/Central IT/Agentext/test",
            "recursive": True
        }))

        print("\nTodos os testes passaram!")


if __name__ == "__main__":
    asyncio.run(main())

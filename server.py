from fastmcp import FastMCP
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse as StarletteJSONResponse
import os
import shutil
import uvicorn

# --- Configuração via variáveis de ambiente ---
SANDBOX_DIR = os.path.abspath(os.environ.get("FILE_MANAGER_SANDBOX", "/tmp/sandbox"))
HOST = os.environ.get("FILE_MANAGER_HOST", "0.0.0.0")
PORT = int(os.environ.get("FILE_MANAGER_PORT", "8000"))
API_KEY = os.environ.get("FILE_MANAGER_API_KEY", "")


class ApiKeyMiddleware:
    """Middleware ASGI puro para autenticação — compatível com SSE streaming."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http" and API_KEY:
            path = scope.get("path", "")
            if not path.startswith("/health") and not path.startswith("/mcp"):
                headers = dict(scope.get("headers", []))
                key = headers.get(b"x-api-key", b"").decode()
                if key != API_KEY:
                    response = StarletteJSONResponse(
                        status_code=401, content={"error": "API key inválida"}
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


# --- MCP server + tools ---
mcp = FastMCP("file-manager")


def _resolve_safe(path: str) -> str:
    """Resolve o caminho e garante que está dentro do diretório sandbox."""
    resolved = os.path.abspath(os.path.join(SANDBOX_DIR, path))
    if not resolved.startswith(SANDBOX_DIR):
        raise ValueError(f"Acesso negado: caminho fora do diretório permitido ({SANDBOX_DIR})")
    return resolved


@mcp.tool()
def create_file(file_path: str, content: str) -> str:
    """Cria um novo arquivo com o conteúdo especificado. Cria diretórios intermediários se necessário. O caminho é relativo ao diretório sandbox."""
    resolved = _resolve_safe(file_path)
    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    with open(resolved, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Arquivo criado com sucesso: {file_path}"


@mcp.tool()
def read_file(file_path: str) -> str:
    """Lê o conteúdo de um arquivo existente. O caminho é relativo ao diretório sandbox."""
    resolved = _resolve_safe(file_path)
    with open(resolved, "r", encoding="utf-8") as f:
        return f.read()


@mcp.tool()
def edit_file(
    file_path: str,
    content: str | None = None,
    old_text: str | None = None,
    new_text: str | None = None,
) -> str:
    """Edita um arquivo existente. Use 'content' para substituir tudo, ou 'old_text'/'new_text' para substituição parcial. O caminho é relativo ao diretório sandbox."""
    resolved = _resolve_safe(file_path)

    if content is not None:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Arquivo substituído com sucesso: {file_path}"

    if old_text is not None and new_text is not None:
        with open(resolved, "r", encoding="utf-8") as f:
            current = f.read()
        if old_text not in current:
            return f"Erro: texto não encontrado no arquivo: '{old_text}'"
        updated = current.replace(old_text, new_text)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(updated)
        return f"Arquivo editado com sucesso: {file_path}"

    return "Erro: forneça 'content' para substituição completa ou 'old_text' e 'new_text' para substituição parcial."


@mcp.tool()
def delete_file(file_path: str, recursive: bool = False) -> str:
    """Exclui um arquivo ou diretório. O caminho é relativo ao diretório sandbox."""
    resolved = _resolve_safe(file_path)
    if os.path.isdir(resolved):
        if recursive:
            shutil.rmtree(resolved)
        else:
            os.rmdir(resolved)
    else:
        os.remove(resolved)
    return f"Excluído com sucesso: {file_path}"


@mcp.tool()
def list_files(dir_path: str = ".") -> str:
    """Lista arquivos e diretórios em um caminho especificado. O caminho é relativo ao diretório sandbox."""
    resolved = _resolve_safe(dir_path)
    entries = os.listdir(resolved)
    if not entries:
        return "(diretório vazio)"
    lines = []
    for name in sorted(entries):
        full = os.path.join(resolved, name)
        prefix = "[DIR]" if os.path.isdir(full) else "[FILE]"
        lines.append(f"{prefix} {name}")
    return "\n".join(lines)


# --- FastAPI app com MCP montado ---
mcp_app = mcp.http_app(transport="streamable-http", stateless_http=True)
app = FastAPI(title="File Manager MCP", version="1.0.0", lifespan=mcp_app.lifespan)

app.add_middleware(ApiKeyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "sandbox": SANDBOX_DIR}


# Monta o MCP server (endpoint: /mcp/mcp)
app.mount("/mcp", mcp_app)


if __name__ == "__main__":
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    print(f"Servidor MCP file-manager iniciando em {HOST}:{PORT}")
    print(f"Diretório sandbox: {SANDBOX_DIR}")
    print(f"Autenticação: {'ativada' if API_KEY else 'desativada'}")
    print(f"MCP endpoint: http://{HOST}:{PORT}/mcp/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    uvicorn.run(app, host=HOST, port=PORT)
else:
    # Vercel serverless — cria o sandbox em /tmp
    os.makedirs(SANDBOX_DIR, exist_ok=True)

from fastmcp import FastMCP
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse as StarletteJSONResponse
import os
import httpx
import uvicorn

# --- Configuração via variáveis de ambiente ---
CLIENT_ID = os.environ.get("CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "")
TENANT_ID = os.environ.get("TENANT_ID", "d483e5ff-b6da-4938-b7c9-0facee9e6746")
SITE_ID = os.environ.get("SHAREPOINT_SITE_ID", "centralitltda.sharepoint.com,7f417076-f263-4c77-8b1f-57e6fe25319a,570f7ea0-5b25-4e23-a834-87b8d9238341")
DRIVE_ID = os.environ.get("SHAREPOINT_DRIVE_ID", "b!dnBBf2Pyd0yLH1fm_iUxmqB-D1clWyNOqDSHuNkjg0GGDSEII2oET6_ZNjHfd57i")
BASE_FOLDER = os.environ.get("SHAREPOINT_BASE_FOLDER", "General/HIPERAUTOMAÇÃO/Outros")
HOST = os.environ.get("FILE_MANAGER_HOST", "0.0.0.0")
PORT = int(os.environ.get("FILE_MANAGER_PORT", "8000"))
API_KEY = os.environ.get("FILE_MANAGER_API_KEY", "")

GRAPH_URL = "https://graph.microsoft.com/v1.0"


class ApiKeyMiddleware:
    """Middleware ASGI puro para autenticação — compatível com streaming."""

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


# --- Microsoft Graph helpers ---

async def _get_token() -> str:
    """Obtém token de acesso via client credentials."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def _build_path(file_path: str) -> str:
    """Constrói o caminho completo dentro do SharePoint."""
    clean = file_path.strip("/")
    if BASE_FOLDER:
        return f"{BASE_FOLDER}/{clean}"
    return clean


async def _graph_headers() -> dict:
    token = await _get_token()
    return {"Authorization": f"Bearer {token}"}


# --- MCP server + tools ---
mcp = FastMCP("file-manager")


@mcp.tool()
async def create_file(file_path: str, content: str) -> str:
    """Cria um novo arquivo no SharePoint com o conteúdo especificado. O caminho é relativo à pasta base configurada."""
    headers = await _graph_headers()
    full_path = _build_path(file_path)
    url = f"{GRAPH_URL}/drives/{DRIVE_ID}/root:/{full_path}:/content"

    async with httpx.AsyncClient() as client:
        resp = await client.put(
            url,
            headers={**headers, "Content-Type": "text/plain"},
            content=content.encode("utf-8"),
        )
        if resp.status_code in (200, 201):
            return f"Arquivo criado com sucesso no SharePoint: {file_path}"
        return f"Erro ao criar arquivo: {resp.status_code} - {resp.text}"


@mcp.tool()
async def read_file(file_path: str) -> str:
    """Lê o conteúdo de um arquivo do SharePoint. O caminho é relativo à pasta base configurada."""
    headers = await _graph_headers()
    full_path = _build_path(file_path)
    url = f"{GRAPH_URL}/drives/{DRIVE_ID}/root:/{full_path}:/content"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        return f"Erro ao ler arquivo: {resp.status_code} - {resp.text}"


@mcp.tool()
async def edit_file(
    file_path: str,
    content: str | None = None,
    old_text: str | None = None,
    new_text: str | None = None,
) -> str:
    """Edita um arquivo no SharePoint. Use 'content' para substituir tudo, ou 'old_text'/'new_text' para substituição parcial. O caminho é relativo à pasta base configurada."""
    if content is not None:
        return await create_file(file_path, content)

    if old_text is not None and new_text is not None:
        current = await read_file(file_path)
        if current.startswith("Erro ao ler"):
            return current
        if old_text not in current:
            return f"Erro: texto não encontrado no arquivo: '{old_text}'"
        updated = current.replace(old_text, new_text)
        return await create_file(file_path, updated)

    return "Erro: forneça 'content' para substituição completa ou 'old_text' e 'new_text' para substituição parcial."


@mcp.tool()
async def delete_file(file_path: str) -> str:
    """Exclui um arquivo ou pasta do SharePoint. O caminho é relativo à pasta base configurada."""
    headers = await _graph_headers()
    full_path = _build_path(file_path)
    url = f"{GRAPH_URL}/drives/{DRIVE_ID}/root:/{full_path}"

    async with httpx.AsyncClient() as client:
        resp = await client.delete(url, headers=headers)
        if resp.status_code == 204:
            return f"Excluído com sucesso: {file_path}"
        return f"Erro ao excluir: {resp.status_code} - {resp.text}"


@mcp.tool()
async def list_files(dir_path: str = ".") -> str:
    """Lista arquivos e diretórios no SharePoint. O caminho é relativo à pasta base configurada. Use '.' para listar a pasta raiz."""
    headers = await _graph_headers()

    if dir_path == ".":
        full_path = BASE_FOLDER
    else:
        full_path = _build_path(dir_path)

    url = f"{GRAPH_URL}/drives/{DRIVE_ID}/root:/{full_path}:/children"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return f"Erro ao listar: {resp.status_code} - {resp.text}"

        items = resp.json().get("value", [])
        if not items:
            return "(diretório vazio)"

        lines = []
        for item in sorted(items, key=lambda x: x["name"]):
            prefix = "[DIR]" if "folder" in item else "[FILE]"
            lines.append(f"{prefix} {item['name']}")
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
    return {"status": "ok", "sharepoint_site": SITE_ID, "base_folder": BASE_FOLDER}


# Monta o MCP server (endpoint: /mcp/mcp)
app.mount("/mcp", mcp_app)


if __name__ == "__main__":
    print(f"Servidor MCP file-manager iniciando em {HOST}:{PORT}")
    print(f"SharePoint: {BASE_FOLDER}")
    print(f"Autenticação: {'ativada' if API_KEY else 'desativada'}")
    print(f"MCP endpoint: http://{HOST}:{PORT}/mcp/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    uvicorn.run(app, host=HOST, port=PORT)

import os
import tempfile
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse

import yt_dlp

app = FastAPI(title="YT Download API", version="1.0.1")


# =========================
# Helpers
# =========================
def _download_sync(url: str, tmpdir: str) -> str:
    """
    Baixa o vídeo de forma síncrona (bloqueante) usando yt-dlp.
    Retorna o caminho do arquivo final.
    """
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",  # tenta garantir mp4 quando possível
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        # "restrictfilenames": True,  # opcional: evita caracteres estranhos no nome
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    return filename


def _check_api_key(value: Optional[str]) -> None:
    """
    Se API_KEY estiver definida no ambiente (Render -> Environment),
    exige header X-API-Key. Faz strip() para evitar erro por espaços.
    """
    required = (os.getenv("API_KEY") or "").strip()
    if not required:
        return  # sem API_KEY definida, não bloqueia

    got = (value or "").strip()
    if got != required:
        raise HTTPException(status_code=401, detail="Unauthorized (invalid API key).")


# =========================
# Routes
# =========================
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug-key")
async def debug_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    required = (os.getenv("API_KEY") or "")
    return {
        "received": x_api_key is not None,
        "received_len": 0 if not x_api_key else len(x_api_key),
        "required_is_set": required.strip() != "",
        "required_len": 0 if not required else len(required.strip()),
        "cookies_path": (os.getenv("YTDLP_COOKIES_PATH") or "").strip(),
        "cookies_path_is_set": (os.getenv("YTDLP_COOKIES_PATH") or "").strip() != "",
        "cookies_file_exists": os.path.exists((os.getenv("YTDLP_COOKIES_PATH") or "").strip()) if (os.getenv("YTDLP_COOKIES_PATH") or "").strip() else False,
    }



@app.get("/download")
async def download_video(
    url: str,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    """
    Exemplo:
      GET /download?url=https://www.youtube.com/watch?v=XXXX
      Header: X-API-Key: <sua-chave>   (se API_KEY estiver definida no ambiente)
    """
    _check_api_key(x_api_key)

    try:
        # Em serviços como Render, /tmp existe e é o lugar certo pra temporários
        tmpdir = tempfile.mkdtemp(prefix="ytdlp_", dir="/tmp")

        filename = await asyncio.to_thread(_download_sync, url, tmpdir)

        if not filename or not os.path.exists(filename):
            raise HTTPException(status_code=500, detail="Arquivo não encontrado após download.")

        return FileResponse(
            path=filename,
            media_type="video/mp4",
            filename=os.path.basename(filename),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao baixar o vídeo: {e}")


# =========================
# Local run (opcional)
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("yt_api:app", host="127.0.0.1", port=8000, reload=True)

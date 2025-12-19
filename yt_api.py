import os
import shutil
import tempfile
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse

import yt_dlp

app = FastAPI(title="YT Download API", version="1.0.3")


def _prepare_cookiefile_writable() -> Optional[str]:
    """
    Se YTDLP_COOKIES_PATH estiver definido, copia o cookies.txt (read-only no Render)
    para um arquivo em /tmp (gravável) e retorna o caminho novo.
    """
    src = (os.getenv("YTDLP_COOKIES_PATH") or "").strip()
    if not src:
        return None
    if not os.path.exists(src):
        raise FileNotFoundError(f"Cookie file not found at {src}")

    os.makedirs("/tmp", exist_ok=True)
    dst = os.path.join("/tmp", f"cookies_{os.getpid()}.txt")
    shutil.copyfile(src, dst)
    return dst


def _download_sync(url: str, tmpdir: str) -> str:
    proxy = (os.getenv("YTDLP_PROXY") or "").strip()
    cookiefile = _prepare_cookiefile_writable()

    ydl_opts = {
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(tmpdir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    if proxy:
        ydl_opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        return filename
    finally:
        # limpa a cópia gravável do cookie (boa prática)
        if cookiefile and os.path.exists(cookiefile):
            try:
                os.remove(cookiefile)
            except Exception:
                pass


def _check_api_key(value: Optional[str]) -> None:
    required = (os.getenv("API_KEY") or "").strip()
    if not required:
        return
    got = (value or "").strip()
    if got != required:
        raise HTTPException(status_code=401, detail="Unauthorized (invalid API key).")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug-key")
async def debug_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    required = (os.getenv("API_KEY") or "")
    cookies_path = (os.getenv("YTDLP_COOKIES_PATH") or "").strip()
    proxy = (os.getenv("YTDLP_PROXY") or "").strip()
    return {
        "received": x_api_key is not None,
        "received_len": 0 if not x_api_key else len(x_api_key),
        "required_is_set": required.strip() != "",
        "required_len": 0 if not required else len(required.strip()),
        "cookies_path": cookies_path,
        "cookies_path_is_set": cookies_path != "",
        "cookies_file_exists": os.path.exists(cookies_path) if cookies_path else False,
        "proxy_is_set": proxy != "",
    }


@app.get("/download")
async def download_video(
    url: str,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
):
    _check_api_key(x_api_key)

    try:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("yt_api:app", host="127.0.0.1", port=8000, reload=True)

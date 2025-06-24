import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from enka_client import fetch_profile, build_from_profile
from renderer import render_card

# ==== Telegram bot integration ====
from bot import dp, bot as tg_bot  # re-use existing bot and dispatcher from bot.py

app = FastAPI(title="HSR Build Card Generator")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/card/{uid}", response_class=Response)
async def card(uid: int, character: Optional[int] = None):
    try:
        profile = await fetch_profile(uid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        build = build_from_profile(profile, uid, character)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    png_bytes = await asyncio.to_thread(render_card, build.dict())
    return Response(content=png_bytes, media_type="image/png")


@app.on_event("startup")
async def _startup_bot():
    # launch bot polling in background task
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling(tg_bot))


@app.on_event("shutdown")
async def _shutdown_bot():
    await tg_bot.session.close() 

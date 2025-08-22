# app.py
import io
import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from playwright.async_api import async_playwright, Error as PlaywrightError

app = FastAPI()

# Basic health
@app.get("/health")
async def health():
    return {"status": "ok"}

# Screenshot endpoint - returns PNG
@app.get("/screenshot")
async def screenshot(url: str = Query(..., description="URL to screenshot (include https://)"),
                     full_page: bool = Query(False)):
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-setuid-sandbox"], headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            screenshot_bytes = await page.screenshot(full_page=full_page)
            await browser.close()
    except PlaywrightError as e:
        raise HTTPException(status_code=500, detail=f"playwright error: {e}")
    return StreamingResponse(io.BytesIO(screenshot_bytes), media_type="image/png")

# Get page HTML
@app.get("/html")
async def page_html(url: str = Query(...)):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox","--disable-setuid-sandbox"], headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()
            await browser.close()
    except PlaywrightError as e:
        raise HTTPException(status_code=500, detail=f"playwright error: {e}")
    return JSONResponse({"url": url, "html": content})

# Run JS and return result
@app.post("/eval")
async def page_eval(url: str = Query(...), script: str = Query(...)):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox","--disable-setuid-sandbox"], headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            result = await page.evaluate(script)
            await browser.close()
    except PlaywrightError as e:
        raise HTTPException(status_code=500, detail=f"playwright error: {e}")
    return {"result": result}

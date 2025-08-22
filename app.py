import asyncio
import base64
import json
import uuid
from typing import Dict, Optional, List

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from browser_use import Browser as BrowserUseBrowser
from browser_use import BrowserConfig
from browser_use.browser.context import BrowserContext, BrowserContextConfig
from browser_use.dom.service import DomService

app = FastAPI(title="Browser Use Tool API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active browser sessions
sessions: Dict[str, dict] = {}


class BrowserActionRequest(BaseModel):
    action: str = Field(..., description="The browser action to perform")
    url: Optional[str] = Field(None, description="URL for navigation or new tab")
    index: Optional[int] = Field(None, description="Element index for interaction")
    text: Optional[str] = Field(None, description="Text for input or search")
    scroll_amount: Optional[int] = Field(None, description="Pixels to scroll")
    tab_id: Optional[int] = Field(None, description="Tab ID for switching tabs")
    query: Optional[str] = Field(None, description="Search query")
    goal: Optional[str] = Field(None, description="Extraction goal")
    keys: Optional[str] = Field(None, description="Keys to send")
    seconds: Optional[int] = Field(None, description="Seconds to wait")


class ToolResultResponse(BaseModel):
    output: Optional[str] = None
    error: Optional[str] = None
    base64_image: Optional[str] = None
    results: Optional[List[dict]] = None


@app.post("/session/create")
async def create_session(
    headless: bool = Query(False, description="Run browser in headless mode"),
    disable_security: bool = Query(True, description="Disable browser security")
):
    """Create a new browser session"""
    session_id = str(uuid.uuid4())
    
    # Initialize browser and context
    browser_config_kwargs = {
        "headless": headless, 
        "disable_security": disable_security,
        "args": ["--no-sandbox", "--disable-setuid-sandbox"]
    }
    
    browser = BrowserUseBrowser(BrowserConfig(**browser_config_kwargs))
    
    context_config = BrowserContextConfig()
    context = await browser.new_context(context_config)
    dom_service = DomService(await context.get_current_page())
    
    # Store session
    sessions[session_id] = {
        "browser": browser,
        "context": context,
        "dom_service": dom_service,
        "lock": asyncio.Lock()
    }
    
    return {"session_id": session_id, "message": "Session created successfully"}


@app.post("/session/{session_id}/execute")
async def execute_action(session_id: str, request: BrowserActionRequest):
    """Execute a browser action"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    async with session["lock"]:
        try:
            context = session["context"]
            browser = session["browser"]
            
            # Navigation actions
            if request.action == "go_to_url":
                if not request.url:
                    return ToolResultResponse(error="URL is required for 'go_to_url' action")
                page = await context.get_current_page()
                await page.goto(request.url)
                await page.wait_for_load_state()
                return ToolResultResponse(output=f"Navigated to {request.url}")
            
            elif request.action == "go_back":
                await context.go_back()
                return ToolResultResponse(output="Navigated back")
            
            elif request.action == "refresh":
                await context.refresh_page()
                return ToolResultResponse(output="Refreshed current page")
            
            elif request.action == "web_search":
                if not request.query:
                    return ToolResultResponse(error="Query is required for 'web_search' action")
                
                # For web search, we'll implement a simple version that uses Google
                search_url = f"https://www.google.com/search?q={request.query}"
                page = await context.get_current_page()
                await page.goto(search_url)
                await page.wait_for_load_state()
                
                # Extract search results (simplified)
                try:
                    results = await page.evaluate('''() => {
                        const results = [];
                        const elements = document.querySelectorAll('div.g');
                        for (const el of elements) {
                            const titleEl = el.querySelector('h3');
                            const linkEl = el.querySelector('a');
                            const descEl = el.querySelector('span[jscontroller]');
                            if (titleEl && linkEl) {
                                results.push({
                                    title: titleEl.innerText,
                                    url: linkEl.href,
                                    description: descEl ? descEl.innerText : ''
                                });
                            }
                        }
                        return results;
                    }''')
                    
                    return ToolResultResponse(
                        output=f"Search results for '{request.query}'",
                        results=results[:5]  # Return top 5 results
                    )
                except Exception as e:
                    return ToolResultResponse(
                        output=f"Navigated to search results for '{request.query}' but couldn't extract them",
                        error=str(e)
                    )
            
            # Element interaction actions
            elif request.action == "click_element":
                if request.index is None:
                    return ToolResultResponse(error="Index is required for 'click_element' action")
                element = await context.get_dom_element_by_index(request.index)
                if not element:
                    return ToolResultResponse(error=f"Element with index {request.index} not found")
                
                try:
                    download_path = await context._click_element_node(element)
                    output = f"Clicked element at index {request.index}"
                    if download_path:
                        output += f" - Downloaded file to {download_path}"
                    return ToolResultResponse(output=output)
                except Exception as e:
                    return ToolResultResponse(error=f"Failed to click element: {str(e)}")
            
            elif request.action == "input_text":
                if request.index is None or not request.text:
                    return ToolResultResponse(error="Index and text are required for 'input_text' action")
                element = await context.get_dom_element_by_index(request.index)
                if not element:
                    return ToolResultResponse(error=f"Element with index {request.index} not found")
                
                try:
                    await context._input_text_element_node(element, request.text)
                    return ToolResultResponse(
                        output=f"Input '{request.text}' into element at index {request.index}"
                    )
                except Exception as e:
                    return ToolResultResponse(error=f"Failed to input text: {str(e)}")
            
            elif request.action == "scroll_down" or request.action == "scroll_up":
                direction = 1 if request.action == "scroll_down" else -1
                amount = (
                    request.scroll_amount
                    if request.scroll_amount is not None
                    else 500  # Default scroll amount
                )
                await context.execute_javascript(
                    f"window.scrollBy(0, {direction * amount});"
                )
                return ToolResultResponse(
                    output=f"Scrolled {'down' if direction > 0 else 'up'} by {amount} pixels"
                )
            
            elif request.action == "scroll_to_text":
                if not request.text:
                    return ToolResultResponse(error="Text is required for 'scroll_to_text' action")
                page = await context.get_current_page()
                try:
                    # Using evaluate to scroll to text
                    await page.evaluate(f'''() => {{
                        const elements = document.querySelectorAll('*');
                        for (const el of elements) {{
                            if (el.textContent && el.textContent.includes('{request.text}')) {{
                                el.scrollIntoView();
                                return;
                            }}
                        }}
                    }}''')
                    return ToolResultResponse(output=f"Scrolled to text: '{request.text}'")
                except Exception as e:
                    return ToolResultResponse(error=f"Failed to scroll to text: {str(e)}")
            
            elif request.action == "send_keys":
                if not request.keys:
                    return ToolResultResponse(error="Keys are required for 'send_keys' action")
                page = await context.get_current_page()
                await page.keyboard.press(request.keys)
                return ToolResultResponse(output=f"Sent keys: {request.keys}")
            
            elif request.action == "get_dropdown_options":
                if request.index is None:
                    return ToolResultResponse(error="Index is required for 'get_dropdown_options' action")
                element = await context.get_dom_element_by_index(request.index)
                if not element:
                    return ToolResultResponse(error=f"Element with index {request.index} not found")
                page = await context.get_current_page()
                options = await page.evaluate(
                    """
                    (xpath) => {
                        const select = document.evaluate(xpath, document, null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (!select) return null;
                        return Array.from(select.options).map(opt => ({
                            text: opt.text,
                            value: opt.value,
                            index: opt.index
                        }));
                    }
                """,
                    element.xpath,
                )
                return ToolResultResponse(output=f"Dropdown options: {options}")
            
            elif request.action == "select_dropdown_option":
                if request.index is None or not request.text:
                    return ToolResultResponse(error="Index and text are required for 'select_dropdown_option' action")
                element = await context.get_dom_element_by_index(request.index)
                if not element:
                    return ToolResultResponse(error=f"Element with index {request.index} not found")
                page = await context.get_current_page()
                await page.select_option(element.xpath, label=request.text)
                return ToolResultResponse(
                    output=f"Selected option '{request.text}' from dropdown at index {request.index}"
                )
            
            # Content extraction actions
            elif request.action == "extract_content":
                if not request.goal:
                    return ToolResultResponse(error="Goal is required for 'extract_content' action")
                
                page = await context.get_current_page()
                
                # Get page content
                content = await page.content()
                
                # Simple extraction based on goal
                if "title" in request.goal.lower():
                    title = await page.title()
                    return ToolResultResponse(output=f"Page title: {title}")
                elif "links" in request.goal.lower():
                    links = await page.evaluate('''() => {
                        return Array.from(document.querySelectorAll('a')).map(a => ({
                            text: a.textContent,
                            href: a.href
                        }));
                    }''')
                    return ToolResultResponse(output=f"Extracted links: {json.dumps(links, indent=2)}")
                else:
                    # Extract all text content as a fallback
                    text_content = await page.evaluate('''() => {
                        return document.body.innerText;
                    }''')
                    return ToolResultResponse(output=f"Page content: {text_content[:2000]}...")
            
            # Tab management actions
            elif request.action == "switch_tab":
                if request.tab_id is None:
                    return ToolResultResponse(error="Tab ID is required for 'switch_tab' action")
                await context.switch_to_tab(request.tab_id)
                page = await context.get_current_page()
                await page.wait_for_load_state()
                return ToolResultResponse(output=f"Switched to tab {request.tab_id}")
            
            elif request.action == "open_tab":
                if not request.url:
                    return ToolResultResponse(error="URL is required for 'open_tab' action")
                await context.create_new_tab(request.url)
                return ToolResultResponse(output=f"Opened new tab with {request.url}")
            
            elif request.action == "close_tab":
                await context.close_current_tab()
                return ToolResultResponse(output="Closed current tab")
            
            # Utility actions
            elif request.action == "wait":
                seconds_to_wait = request.seconds if request.seconds is not None else 3
                await asyncio.sleep(seconds_to_wait)
                return ToolResultResponse(output=f"Waited for {seconds_to_wait} seconds")
            
            else:
                return ToolResultResponse(error=f"Unknown action: {request.action}")
        
        except Exception as e:
            return ToolResultResponse(error=f"Browser action '{request.action}' failed: {str(e)}")


@app.get("/session/{session_id}/state")
async def get_state(session_id: str):
    """Get the current browser state"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    context = session["context"]
    
    try:
        # Get current page
        page = await context.get_current_page()
        
        # Get URL and title
        url = page.url
        title = await page.title()
        
        # Take a screenshot
        screenshot = await page.screenshot(
            full_page=True, animations="disabled", type="jpeg", quality=80
        )
        screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
        
        # Get interactive elements (simplified)
        elements = await page.evaluate('''() => {
            const interactive = [];
            const selectors = ['a', 'button', 'input', 'select', 'textarea', '[onclick]', '[role=button]'];
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        interactive.push({
                            tag: el.tagName,
                            text: el.textContent?.substring(0, 50) || '',
                            type: el.type || '',
                            id: el.id || '',
                            class: el.className || ''
                        });
                    }
                });
            });
            return interactive.slice(0, 20); // Limit to first 20 elements
        }''')
        
        # Build state info
        state_info = {
            "url": url,
            "title": title,
            "interactive_elements": elements,
            "help": "Use element indices to interact with page elements"
        }
        
        return ToolResultResponse(
            output=json.dumps(state_info, indent=2),
            base64_image=screenshot_b64
        )
    except Exception as e:
        return ToolResultResponse(error=f"Failed to get browser state: {str(e)}")


@app.delete("/session/{session_id}")
async def close_session(session_id: str):
    """Close a browser session"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[session_id]
    
    try:
        if session["context"] is not None:
            await session["context"].close()
        if session["browser"] is not None:
            await session["browser"].close()
        
        del sessions[session_id]
        return {"status": "success", "message": "Session closed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to close session: {str(e)}")


@app.get("/")
async def root():
    return {"message": "Browser Use Tool API is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

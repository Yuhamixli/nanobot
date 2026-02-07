"""Browser automation (RPA) tool using Playwright.

Enables the agent to drive a browser: navigate, fill forms, click, extract content.
Useful for external web apps (e.g. 商网) that require login or JavaScript.

Requires: pip install playwright && playwright install chromium
"""

from typing import Any

from nanobot.agent.tools.base import Tool


class BrowserAutomationTool(Tool):
    """RPA tool: navigate, fill, click, extract on a web page."""

    name = "browser_automation"
    description = (
        "Automate a browser: open URL, fill inputs, click elements, extract text. "
        "Use for web apps that need login or JavaScript. Steps: navigate (url), "
        "fill (selector, value), click (selector), select (selector, value), "
        "extract (selector, optional attribute like 'textContent' or 'href')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Initial URL to open (used if first step is not navigate)",
            },
            "steps": {
                "type": "array",
                "description": "List of actions in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["navigate", "fill", "click", "select", "extract", "wait"],
                            "description": "Action type",
                        },
                        "url": {"type": "string", "description": "For navigate: URL to open"},
                        "selector": {
                            "type": "string",
                            "description": "CSS selector for fill/click/select/extract",
                        },
                        "value": {
                            "type": "string",
                            "description": "For fill/select: value to set",
                        },
                        "attribute": {
                            "type": "string",
                            "description": "For extract: e.g. textContent, innerText, href (default textContent)",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "For wait: milliseconds to wait",
                        },
                    },
                    "required": ["action"],
                },
            },
            "headless": {
                "type": "boolean",
                "description": "Run browser headless (default true)",
                "default": True,
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Default step timeout in ms",
                "default": 30000,
            },
        },
        "required": ["steps"],
    }

    def __init__(self, default_timeout_ms: int = 30000):
        self.default_timeout_ms = default_timeout_ms

    async def execute(
        self,
        steps: list[dict[str, Any]],
        url: str | None = None,
        headless: bool = True,
        timeout_ms: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return (
                "Error: Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        timeout = timeout_ms or self.default_timeout_ms
        results: list[str] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                page.set_default_timeout(timeout)

                current_url = url or "about:blank"
                if url:
                    await page.goto(url, wait_until="domcontentloaded")
                    current_url = page.url
                    results.append(f"Navigated to {current_url}")

                for i, step in enumerate(steps):
                    action = (step.get("action") or "").lower()
                    if not action:
                        results.append(f"Step {i + 1}: missing action, skipped")
                        continue

                    try:
                        if action == "navigate":
                            u = step.get("url") or current_url
                            await page.goto(u, wait_until="domcontentloaded")
                            current_url = page.url
                            results.append(f"Step {i + 1}: navigated to {current_url}")

                        elif action == "wait":
                            t = step.get("timeout", 1000)
                            await page.wait_for_timeout(t)
                            results.append(f"Step {i + 1}: waited {t}ms")

                        elif action == "fill":
                            sel = step.get("selector")
                            val = step.get("value", "")
                            if not sel:
                                results.append(f"Step {i + 1}: fill requires 'selector'")
                                continue
                            await page.wait_for_selector(sel, state="visible")
                            await page.fill(sel, val)
                            results.append(f"Step {i + 1}: filled {sel}")

                        elif action == "click":
                            sel = step.get("selector")
                            if not sel:
                                results.append(f"Step {i + 1}: click requires 'selector'")
                                continue
                            await page.wait_for_selector(sel, state="visible")
                            await page.click(sel)
                            results.append(f"Step {i + 1}: clicked {sel}")

                        elif action == "select":
                            sel = step.get("selector")
                            val = step.get("value", "")
                            if not sel:
                                results.append(f"Step {i + 1}: select requires 'selector'")
                                continue
                            await page.wait_for_selector(sel, state="visible")
                            await page.select_option(sel, value=val)
                            results.append(f"Step {i + 1}: selected {val} in {sel}")

                        elif action == "extract":
                            sel = step.get("selector")
                            attr = step.get("attribute") or "textContent"
                            if not sel:
                                results.append(f"Step {i + 1}: extract requires 'selector'")
                                continue
                            await page.wait_for_selector(sel, state="attached")
                            if attr in ("textContent", "innerText", "innerHTML"):
                                el = await page.query_selector(sel)
                                text = await el.get_attribute(attr) if el else None
                            else:
                                text = await page.get_attribute(sel, attr)
                            out = (text or "").strip()
                            if len(out) > 2000:
                                out = out[:2000] + "..."
                            results.append(f"Step {i + 1} (extract): {out}")

                        else:
                            results.append(f"Step {i + 1}: unknown action '{action}'")
                    except Exception as e:
                        results.append(f"Step {i + 1} error: {e}")

            finally:
                await browser.close()

        return "\n".join(results)

"""
Enhanced Playwright Manager with connection pooling, retry logic, and performance monitoring.

This module provides a robust Playwright browser management system with:
- Browser instance pooling for better resource management
- Automatic retry logic with exponential backoff
- Comprehensive error handling for Playwright-specific exceptions
- Performance monitoring and metrics collection
- Advanced wait strategies for dynamic content
- Concurrent page processing capabilities
"""

import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
    )
    from playwright.async_api import Error as PlaywrightError
    from playwright.async_api import (
        Page,
        TimeoutError,
        async_playwright,
    )

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserEngine(Enum):
    """Supported browser engines."""

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


@dataclass
class BrowserConfig:
    """Configuration for browser instances."""

    engine: BrowserEngine = BrowserEngine.CHROMIUM
    headless: bool = True
    timeout: int = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: Optional[str] = None
    proxy: Optional[Dict[str, str]] = None
    extra_args: List[str] = field(default_factory=list)

    def get_launch_args(self) -> List[str]:
        """Get optimized browser launch arguments."""
        args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--single-process",  # Reduces memory usage
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-blink-features=AutomationControlled",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-plugins",
            "--disable-images",  # Optional: disable images for faster loading
            "--disable-javascript-harmony-shipping",
            "--memory-pressure-off",
            "--max_old_space_size=4096",
        ]
        return args + self.extra_args


@dataclass
class PageMetrics:
    """Metrics for page load performance."""

    url: str
    load_time: float
    render_time: float
    total_time: float
    success: bool
    error: Optional[str] = None
    retry_count: int = 0
    content_size: int = 0
    resources_loaded: int = 0


class PlaywrightManager:
    """
    Enhanced Playwright manager with pooling, retry logic, and monitoring.
    """

    def __init__(
        self,
        config: Optional[BrowserConfig] = None,
        max_browsers: int = 3,
        max_contexts: int = 10,
        max_pages_per_context: int = 5,
        logger: Optional[logging.Logger] = None,
    ):
        self.config = config or BrowserConfig()
        self.max_browsers = max_browsers
        self.max_contexts = max_contexts
        self.max_pages_per_context = max_pages_per_context
        self.logger = logger or logging.getLogger(__name__)

        # Resource pools
        self.playwright = None
        self.browsers: List[Browser] = []
        self.available_browsers: deque = deque()
        self.contexts: Dict[Browser, List[BrowserContext]] = {}
        self.pages: Dict[BrowserContext, List[Page]] = {}

        # Metrics tracking
        self.metrics: List[PageMetrics] = []
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0

        # Synchronization
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize Playwright and create browser pool."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            if not PLAYWRIGHT_AVAILABLE:
                raise RuntimeError("Playwright is not installed")

            self.playwright = await async_playwright().start()

            # Create initial browser pool
            for _ in range(min(2, self.max_browsers)):
                browser = await self._create_browser()
                self.browsers.append(browser)
                self.available_browsers.append(browser)
                self.contexts[browser] = []

            self._initialized = True
            self.logger.info(
                f"Playwright manager initialized with {len(self.browsers)} browsers"
            )

    async def _create_browser(self) -> Browser:
        """Create a new browser instance with optimized settings."""
        launch_options = {
            "headless": self.config.headless,
            "args": self.config.get_launch_args(),
        }

        if self.config.proxy:
            launch_options["proxy"] = self.config.proxy

        engine = getattr(self.playwright, self.config.engine.value)
        browser = await engine.launch(**launch_options)

        self.logger.debug(f"Created new {self.config.engine.value} browser instance")
        return browser

    async def _get_or_create_browser(self) -> Browser:
        """Get an available browser or create a new one if needed."""
        async with self._lock:
            # Try to get an available browser
            if self.available_browsers:
                return self.available_browsers.popleft()

            # Create new browser if under limit
            if len(self.browsers) < self.max_browsers:
                browser = await self._create_browser()
                self.browsers.append(browser)
                self.contexts[browser] = []
                return browser

            # Wait for a browser to become available
            while not self.available_browsers:
                await asyncio.sleep(0.1)

            return self.available_browsers.popleft()

    async def _get_or_create_context(self, browser: Browser) -> BrowserContext:
        """Get or create a browser context with proper configuration."""
        contexts = self.contexts.get(browser, [])

        # Reuse existing context if available
        for context in contexts:
            if (
                context not in self.pages
                or len(self.pages.get(context, [])) < self.max_pages_per_context
            ):
                return context

        # Create new context if under limit
        if len(contexts) < self.max_contexts:
            context_options = {
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                "ignore_https_errors": True,
            }

            if self.config.user_agent:
                context_options["user_agent"] = self.config.user_agent

            context = await browser.new_context(**context_options)
            contexts.append(context)
            self.contexts[browser] = contexts
            self.pages[context] = []

            # Set default timeout for the context
            context.set_default_timeout(self.config.timeout)

            return context

        # Use least loaded context
        return min(contexts, key=lambda c: len(self.pages.get(c, [])))

    @asynccontextmanager
    async def get_page(self, url: Optional[str] = None):
        """
        Get a page from the pool with automatic resource management.

        Usage:
            async with manager.get_page() as page:
                await page.goto(url)
                content = await page.content()
        """
        if not self._initialized:
            await self.initialize()

        browser = await self._get_or_create_browser()
        context = None
        page = None

        try:
            context = await self._get_or_create_context(browser)
            page = await context.new_page()

            # Track the page
            if context in self.pages:
                self.pages[context].append(page)

            # Enable request interception for metrics
            await self._setup_page_monitoring(page)

            yield page

        finally:
            # Cleanup
            if page:
                try:
                    await page.close()
                except:
                    pass

                if context in self.pages and page in self.pages[context]:
                    self.pages[context].remove(page)

            # Return browser to pool
            if browser not in self.available_browsers:
                self.available_browsers.append(browser)

    async def _setup_page_monitoring(self, page: Page):
        """Set up monitoring for page performance."""
        resources_loaded = [0]

        async def on_request(request):
            self.logger.debug(f"Request: {request.method} {request.url}")

        async def on_response(response):
            resources_loaded[0] += 1
            self.logger.debug(f"Response: {response.status} {response.url}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.resources_loaded = resources_loaded

    async def render_page(
        self,
        url: str,
        max_retries: int = 3,
        wait_strategy: str = "networkidle",
        wait_for_selectors: Optional[List[str]] = None,
        execute_script: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Render a page with retry logic and comprehensive error handling.

        Args:
            url: URL to render
            max_retries: Maximum number of retry attempts
            wait_strategy: Wait strategy ('load', 'domcontentloaded', 'networkidle')
            wait_for_selectors: List of selectors to wait for
            execute_script: JavaScript to execute after page load

        Returns:
            Dictionary with rendered content and metrics
        """
        metrics = PageMetrics(
            url=url, load_time=0, render_time=0, total_time=0, success=False
        )
        start_time = time.time()
        last_error = None

        for attempt in range(max_retries):
            try:
                metrics.retry_count = attempt
                time.time()

                async with self.get_page() as page:
                    # Navigate to the page
                    load_start = time.time()
                    response = await page.goto(
                        url,
                        wait_until=wait_strategy,
                        timeout=self.config.timeout,
                    )
                    metrics.load_time = time.time() - load_start

                    # Check response status
                    if response and response.status >= 400:
                        raise PlaywrightError(f"HTTP {response.status} error")

                    # Wait for dynamic content
                    render_start = time.time()
                    await self._wait_for_content(page, wait_for_selectors)

                    # Execute custom script if provided
                    if execute_script:
                        await page.evaluate(execute_script)

                    # Extract content
                    content = await page.content()
                    title = await page.title()

                    # Extract links and resources
                    links = await page.evaluate(
                        """
                        () => Array.from(document.querySelectorAll('a[href]'))
                               .map(a => a.href)
                               .filter(href => href && href.startsWith('http'))
                    """
                    )

                    # Extract meta information
                    meta = await page.evaluate(
                        """
                        () => {
                            const metas = {};
                            document.querySelectorAll(
                                'meta[name], meta[property]'
                            ).forEach(meta => {
                                const key = meta.getAttribute('name') ||
                                    meta.getAttribute('property');
                                if (key) metas[key] = meta.getAttribute('content');
                            });
                            return metas;
                        }
                    """
                    )

                    # Extract JSON-LD data
                    json_ld = await page.evaluate(
                        """
                        () => {
                            const scripts = Array.from(
                                document.querySelectorAll('script[type="application/ld+json"]')
                            );
                            return scripts.map(s => {
                                try { return JSON.parse(s.textContent); }
                                catch { return null; }
                            }).filter(Boolean);
                        }
                    """
                    )

                    metrics.render_time = time.time() - render_start
                    metrics.content_size = len(content)
                    metrics.resources_loaded = getattr(page, "resources_loaded", [0])[0]
                    metrics.success = True

                    self.successful_requests += 1
                    self.metrics.append(metrics)  # Add metrics to tracking list

                    return {
                        "success": True,
                        "content": content,
                        "title": title,
                        "links": links,
                        "meta": meta,
                        "json_ld": json_ld,
                        "metrics": metrics,
                        "url": url,
                    }

            except TimeoutError:
                last_error = f"Timeout after {self.config.timeout}ms"
                self.logger.warning(
                    f"Timeout loading {url} (attempt {attempt + 1}/{max_retries})"
                )

                # Increase timeout for next attempt
                self.config.timeout = min(self.config.timeout * 1.5, 60000)

            except PlaywrightError as e:
                last_error = str(e)
                self.logger.warning(
                    f"Playwright error for {url}: {e} (attempt {attempt + 1}/{max_retries})"
                )

            except Exception as e:
                last_error = str(e)
                self.logger.error(
                    f"Unexpected error rendering {url}: {e} (attempt {attempt + 1}/{max_retries})"
                )

            # Exponential backoff
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)

        # All retries failed
        metrics.total_time = time.time() - start_time
        metrics.error = last_error
        self.failed_requests += 1
        self.metrics.append(metrics)  # Add failed metrics to tracking list

        return {
            "success": False,
            "error": last_error,
            "metrics": metrics,
            "url": url,
        }

    async def _wait_for_content(
        self, page: Page, selectors: Optional[List[str]] = None
    ):
        """
        Advanced wait strategy for dynamic content.
        """
        # Default selectors for common frameworks
        default_selectors = [
            "[data-reactroot]",
            "[data-react-root]",
            "[ng-app]",
            "[ng-controller]",
            "#app",
            "#root",
            ".app",
            ".content-loaded",
            "[data-vue-app]",
            "[data-server-rendered]",
        ]

        selectors = selectors or default_selectors

        # Try to wait for any of the selectors
        wait_tasks = []
        for selector in selectors:
            wait_tasks.append(self._wait_for_selector_safe(page, selector))

        # Wait for at least one selector or timeout
        if wait_tasks:
            await asyncio.gather(*wait_tasks, return_exceptions=True)

        # Additional wait for JavaScript execution
        await page.wait_for_load_state("networkidle")

        # Check for lazy-loaded content
        await self._scroll_and_wait(page)

    async def _wait_for_selector_safe(
        self, page: Page, selector: str, timeout: int = 2000
    ):
        """Safely wait for a selector without throwing exceptions."""
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            self.logger.debug(f"Found selector: {selector}")
        except:
            pass

    async def _scroll_and_wait(self, page: Page):
        """Scroll the page to trigger lazy-loaded content."""
        try:
            # Scroll to bottom to trigger lazy loading
            await page.evaluate(
                """
                () => {
                    return new Promise((resolve) => {
                        let totalHeight = 0;
                        const distance = 100;
                        const timer = setInterval(() => {
                            const scrollHeight = document.body.scrollHeight;
                            window.scrollBy(0, distance);
                            totalHeight += distance;

                            if(totalHeight >= scrollHeight){
                                clearInterval(timer);
                                window.scrollTo(0, 0);  // Scroll back to top
                                resolve();
                            }
                        }, 100);

                        // Timeout after 3 seconds
                        setTimeout(() => {
                            clearInterval(timer);
                            resolve();
                        }, 3000);
                    });
                }
            """
            )
        except:
            pass

    async def render_batch(
        self, urls: List[str], max_concurrent: int = 5, **render_kwargs
    ) -> List[Dict[str, Any]]:
        """
        Render multiple URLs concurrently with rate limiting.

        Args:
            urls: List of URLs to render
            max_concurrent: Maximum concurrent renders
            **render_kwargs: Additional arguments for render_page

        Returns:
            List of render results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def render_with_limit(url):
            async with semaphore:
                return await self.render_page(url, **render_kwargs)

        tasks = [render_with_limit(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions in results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(
                    {
                        "success": False,
                        "error": str(result),
                        "url": urls[i],
                    }
                )
            else:
                processed_results.append(result)

        return processed_results

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of performance metrics."""
        if not self.metrics:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "success_rate": 0,
            }

        successful_metrics = [m for m in self.metrics if m.success]

        return {
            "total_requests": len(self.metrics),
            "successful_requests": len(successful_metrics),
            "failed_requests": len(self.metrics) - len(successful_metrics),
            "success_rate": (
                len(successful_metrics) / len(self.metrics) * 100 if self.metrics else 0
            ),
            "avg_load_time": (
                sum(m.load_time for m in successful_metrics) / len(successful_metrics)
                if successful_metrics
                else 0
            ),
            "avg_render_time": (
                sum(m.render_time for m in successful_metrics) / len(successful_metrics)
                if successful_metrics
                else 0
            ),
            "avg_content_size": (
                sum(m.content_size for m in successful_metrics)
                / len(successful_metrics)
                if successful_metrics
                else 0
            ),
            "avg_resources": (
                sum(m.resources_loaded for m in successful_metrics)
                / len(successful_metrics)
                if successful_metrics
                else 0
            ),
            "avg_retry_count": (
                sum(m.retry_count for m in self.metrics) / len(self.metrics)
                if self.metrics
                else 0
            ),
        }

    async def cleanup(self):
        """Clean up all browser resources."""
        self.logger.info("Cleaning up Playwright resources")

        # Close all pages
        for context, pages in self.pages.items():
            for page in pages:
                try:
                    await page.close()
                except:
                    pass

        # Close all contexts
        for browser, contexts in self.contexts.items():
            for context in contexts:
                try:
                    await context.close()
                except:
                    pass

        # Close all browsers
        for browser in self.browsers:
            try:
                await browser.close()
            except:
                pass

        # Stop Playwright
        if self.playwright:
            await self.playwright.stop()

        self.browsers.clear()
        self.available_browsers.clear()
        self.contexts.clear()
        self.pages.clear()
        self._initialized = False

        self.logger.info(
            f"Cleanup complete. Final metrics: {self.get_metrics_summary()}"
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()


# Convenience function for backwards compatibility
async def create_playwright_manager(
    config: Optional[BrowserConfig] = None,
) -> PlaywrightManager:
    """Create and initialize a Playwright manager."""
    manager = PlaywrightManager(config=config)
    await manager.initialize()
    return manager

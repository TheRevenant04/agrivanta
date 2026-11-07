"""Worker process: isolate Chromium's runtime files and stdout from Django."""

import sys

from playwright.sync_api import sync_playwright


def main():
    html = sys.stdin.buffer.read().decode("utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=sys.argv[1],
            headless=True,
            chromium_sandbox=True,
            args=["--disable-background-networking"],
            proxy={"server": "http://127.0.0.1:9", "bypass": "<-loopback>"},
            timeout=30000,
        )
        try:
            context = browser.new_context(
                java_script_enabled=False, service_workers="block",
            )
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(html, wait_until="load", timeout=30000)
            pdf = page.pdf(
                format="A4", print_background=True, prefer_css_page_size=True
            )
            sys.stdout.buffer.write(pdf)
        finally:
            browser.close()


if __name__ == "__main__":
    main()

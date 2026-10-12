"""Real-browser checks using only an isolated, temporary test database/server."""

from pathlib import Path
import argparse, json, os, re, secrets, socket, subprocess, sys, tempfile, time
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    if not (ROOT / "frontend/dist/index.html").exists():
        raise SystemExit("Run npm ci and npm run build in frontend first.")
    output = (
        Path(args.output).resolve()
        if args.output
        else Path(tempfile.mkdtemp(prefix="pulseiq-browser-output-"))
    )
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pulseiq-browser-db-") as temp:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        password = "qa-" + secrets.token_urlsafe(20)
        env = dict(
            os.environ,
            DATABASE_URL="sqlite:///" + str(Path(temp) / "app.sqlite"),
            ENVIRONMENT="test",
            APP_SECRET=secrets.token_urlsafe(40),
            BOOTSTRAP_ADMIN_PASSWORD=password,
            COOKIE_SECURE="false",
            SEED_DEMO="true",
            DEMO_STUDENTS="1000",
            SOURCE_KIND="none",
        )
        address = f"http://127.0.0.1:{port}"
        log = (output / "server.log").open("w")
        process = None
        checks = []
        browser_errors = []

        def start():
            nonlocal process
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("QA server exited. See server.log.")
                try:
                    if (
                        httpx.get(
                            address + "/health", timeout=1, trust_env=False
                        ).status_code
                        == 200
                    ):
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.15)
            raise RuntimeError("QA server did not become healthy in 45 seconds.")

        def stop():
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        def mark(name):
            checks.append(name)
            print("PASS", name, flush=True)

        def nav(page, name):
            page.locator("nav").get_by_role(
                "button", name=re.compile("^" + re.escape(name))
            ).click()

        try:
            start()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1050})
                context.set_default_timeout(10000)
                page = context.new_page()
                page.on("pageerror", lambda e: browser_errors.append(str(e)))
                page.goto(address)
                expect(
                    page.get_by_role("heading", name="Welcome to PULSEIQ")
                ).to_be_visible()
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator(".metric strong").first).to_have_text(
                    "1000", timeout=20000
                )
                expect(
                    page.get_by_text("Fictional demo records", exact=True)
                ).to_be_visible()
                page.screenshot(path=str(output / "overview.png"), full_page=True)
                mark("Login, 1000-student overview and charts")

                page.get_by_role("button", name="DEMO0001", exact=True).click()
                expect(page.locator(".metrics .metric strong").first).to_have_text(
                    "68.0", timeout=15000
                )
                expect(
                    page.locator("td small").filter(
                        has_text="Fictional college demo / placement"
                    )
                ).to_be_visible()
                page.screenshot(
                    path=str(output / "student-profile.png"), full_page=True
                )
                mark("Student profile, reference score and provenance")

                page.get_by_label("Owner alias", exact=True).fill("QA mentor")
                action = "Practice coding and review the next assessment together."
                page.get_by_label("Editable action", exact=True).fill(action)
                with page.expect_response(
                    lambda r: r.request.method == "POST"
                    and r.url.endswith("/api/actions")
                ) as result:
                    page.get_by_role(
                        "button", name="Create support action", exact=False
                    ).click()
                assert result.value.status == 201
                nav(page, "Action Board")
                expect(page.locator(".lane-planned .action-card")).to_have_count(1)
                page.locator(".lane-planned .action-card").click()
                expect(page.locator(".history strong")).to_have_count(1)
                page.get_by_label("Status", exact=True).select_option("Reviewed")
                page.get_by_label("Review note", exact=True).fill(
                    "Workshop completed; discuss next mock assessment."
                )
                page.get_by_role("button", name="Save revision").click()
                expect(page.locator(".modal")).to_have_count(0)
                expect(page.locator(".lane-reviewed .action-card")).to_have_count(1)
                mark("Create and review a saved Action Board item")

                page.locator(".lane-reviewed .action-card").click()
                expect(page.locator(".history strong")).to_have_count(2)
                page.get_by_label("Status", exact=True).select_option("In progress")
                page.get_by_label("Review note", exact=True).fill(
                    "Reopened to agree on additional practice."
                )
                page.get_by_role("button", name="Save revision").click()
                expect(page.locator(".lane-in-progress .action-card")).to_have_count(1)
                page.screenshot(path=str(output / "action-board.png"), full_page=True)
                stop()
                start()
                page.reload()
                expect(page.locator(".metric strong").first).to_have_text(
                    "1000", timeout=15000
                )
                nav(page, "Action Board")
                expect(page.locator(".lane-in-progress .action-card")).to_have_count(1)
                page.locator(".lane-in-progress .action-card").click()
                expect(page.locator(".history strong")).to_have_count(3)
                expect(page.locator(".history strong").last).to_have_text(
                    "Reopened · admin"
                )
                page.get_by_role("button", name="Close action editor").click()
                mark("Reopen, three revisions and persistence across backend restart")

                nav(page, "What-if Simulator")
                for label in ["Aptitude", "Coding", "Interview"]:
                    slider = page.get_by_role("slider", name=label, exact=True)
                    slider.press("End")
                    for _ in range(20):
                        slider.press("ArrowLeft")
                page.get_by_role(
                    "button", name="Calculate scenario", exact=True
                ).click()
                expect(page.locator(".comparison h2").first).to_have_text(
                    "68.0", timeout=15000
                )
                expect(page.locator(".comparison h2").last).to_have_text("78.0")
                page.wait_for_timeout(500)
                expect(page.locator(".comparison")).to_be_visible()
                nav(page, "Student Profile")
                expect(page.locator(".metrics .metric strong").first).to_have_text(
                    "68.0"
                )
                mark("What-if result stays visible and baseline stays unchanged")

                nav(page, "Connections")
                expect(page.get_by_role("heading", name="Staff access")).to_be_visible()
                expect(
                    page.get_by_role("button", name="Refresh from institution")
                ).to_be_disabled()
                page.get_by_label("Username", exact=True).fill("qa.faculty")
                page.get_by_label("Initial password", exact=True).fill(password)
                page.get_by_label("Computer Science", exact=True).check()
                page.get_by_role(
                    "button", name="Create staff account", exact=True
                ).click()
                expect(
                    page.get_by_role("cell", name="qa.faculty", exact=True)
                ).to_be_visible()
                page.screenshot(path=str(output / "connections.png"), full_page=True)
                page.get_by_role("button", name="Sign out", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Welcome to PULSEIQ")
                ).to_be_visible()
                page.get_by_label("Username", exact=True).fill("qa.faculty")
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator(".metric strong").first).to_have_text(
                    "250", timeout=15000
                )
                expect(
                    page.locator("nav").get_by_role(
                        "button", name="Connections", exact=True
                    )
                ).to_have_count(0)
                nav(page, "Action Board")
                expect(page.locator(".action-card")).to_have_count(1)
                mark(
                    "Create faculty user, scope to 250 authorized students and actions"
                )

                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=str(output / "mobile-board.png"), full_page=True)
                width = page.evaluate(
                    "({viewport:innerWidth,body:document.body.scrollWidth})"
                )
                assert width["body"] <= width["viewport"] + 1, width
                expect(page.locator(".lane")).to_have_count(4)
                mark("Mobile Action Board without horizontal page overflow")
                assert not browser_errors, browser_errors
                browser.close()
                (output / "results.json").write_text(
                    json.dumps(
                        {
                            "checks": checks,
                            "page_errors": browser_errors,
                            "status": "passed",
                        },
                        indent=2,
                    )
                )
        except Exception:
            try:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception:
                pass
            (output / "results.json").write_text(
                json.dumps(
                    {
                        "checks": checks,
                        "page_errors": browser_errors,
                        "status": "failed",
                    },
                    indent=2,
                )
            )
            raise
        finally:
            stop()
            log.close()
    print("Browser results:", output, flush=True)


if __name__ == "__main__":
    main()

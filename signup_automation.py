#!/usr/bin/env python3
"""
Fully automated signup flow for https://authorized-partner.vercel.app

The flow is a multi-page wizard (terms -> details -> ... -> done). Instead of
hard-coding one selector per field, the script runs a generic *step loop*:

    1. describe every visible field on the current page (label / name / placeholder)
    2. map it to a value from test_data.json (see FIELD_RULES)
    3. fill inputs, pick dropdown options, tick checkboxes/radios, upload files
    4. click the primary action button (Continue / Next / Submit ...)
    5. detect success, or detect that the page did not advance (validation error)

Every step is logged and screenshotted; a Markdown + JSON test report is written
to reports/latest/ on each run.

Usage:
    python signup_automation.py                # headless
    python signup_automation.py --headed --slow-mo 300
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
import traceback
from datetime import datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeout

ROOT = Path(__file__).parent
BASE_URL = os.getenv("BASE_URL", "https://authorized-partner.vercel.app").rstrip("/")
REGISTER_URL = f"{BASE_URL}/register"
REPORT_DIR = ROOT / "reports" / "latest"
ASSET_DIR = ROOT / "assets"

# --------------------------------------------------------------------------- #
# Field mapping: first regex that matches "label name id placeholder aria" wins.
# Order matters (specific before generic). Extra rules can be supplied through
# "field_overrides" in test_data.json: {"regex": "value"} and are checked first.
# --------------------------------------------------------------------------- #
FIELD_RULES: list[tuple[str, str]] = [
    (r"otp|verification.?code|one.?time|\bpin\b", "otp"),
    (r"pass", "password"),
    (r"e-?mail", "email"),
    (r"phone|mobile|\btel|whats.?app|contact.?(no\b|number)", "phone"),
    (r"first.?name|given.?name|fname", "first_name"),
    (r"last.?name|sur.?name|family.?name|lname", "last_name"),
    (r"web.?site|\burl\b|link", "website"),
    (r"zip|postal|post.?code", "postal_code"),
    (r"agency|company|business|organi[sz]ation|firm|institution", "agency_name"),
    (r"full.?name|your name|contact.?person|^\s*name\b", "full_name"),
    (r"city|town", "city"),
    (r"state|province|region|district", "state"),
    (r"country|nation", "country"),
    (r"address|street|location", "address"),
    (r"licen[sc]e|registration.?(no|num)|reg\.?.?(no|num)|\bpan\b|\bvat\b|\btax\b|\bgst\b", "registration_number"),
    (r"experience|years", "experience_years"),
    (r"designation|position|job.?title|\brole\b", "designation"),
    (r"descri|about|message|comment|\bbio\b|note|remark|why", "description"),
    (r"birth|dob|date", "date"),
    (r"student|volume|how many|number of|count|total", "number"),
]

NEXT_RE = re.compile(
    r"^\s*(continue|next|submit|register|sign\s*up|create(\s+account)?|finish|complete|"
    r"save(\s*(&|and)\s*continue)?|proceed|verify|confirm|get started|send)\b.*$",
    re.I,
)
BAD_BUTTON_RE = re.compile(r"back|previous|cancel|log\s*in|login|skip|resend|close", re.I)

SUCCESS_URL_RE = re.compile(r"/(dashboard|success|thank|pending|verify|welcome|login|onboarding-complete)", re.I)
SUCCESS_TEXT_RE = re.compile(
    r"successfully (registered|created|submitted)|registration (is )?(successful|complete)|"
    r"account (has been )?created|thank you for (registering|signing|joining)|"
    r"(pending|awaiting) (approval|review)|under review|check your (email|inbox)|"
    r"verification (link|email) (has been )?sent|application (has been )?(received|submitted)",
    re.I,
)

VISIBLE_FIELD_PARTS = [
    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=file])"
    ":not([type=checkbox]):not([type=radio]):not([type=image]):not([type=reset])",
    "textarea",
    "select",
    "[role=combobox]:not(input)",
]
VISIBLE_FIELDS = ",".join(p + ":visible" for p in VISIBLE_FIELD_PARTS)

JS_DESCRIBE = """
el => {
  const clean = n => {  // label text without the wrapped control's own text/options
    const c = n.cloneNode(true);
    c.querySelectorAll('select,input,textarea,button,option').forEach(x => x.remove());
    return (c.textContent || '').replace(/\\s+/g, ' ').trim();
  };
  let label = (el.labels && el.labels[0]) ? clean(el.labels[0]) : '';
  if (!label) {
    let p = el.parentElement;
    for (let i = 0; i < 4 && p && !label; i++, p = p.parentElement) {
      const l = p.querySelector('label'); if (l) label = clean(l);
    }
  }
  return {
    tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(),
    name: el.name || '', id: el.id || '', ph: el.placeholder || '',
    aria: el.getAttribute('aria-label') || '', role: el.getAttribute('role') || '',
    label: label, value: el.value || '', text: (el.innerText || '').trim(),
    disabled: !!el.disabled, readonly: !!el.readOnly
  };
}
"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def load_data() -> dict:
    data = json.loads((ROOT / "test_data.json").read_text(encoding="utf-8"))
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    data["email"] = os.getenv("TEST_EMAIL") or data["email_template"].format(ts=ts)
    data["password"] = os.getenv("TEST_PASSWORD", data["password"])

    otp = (os.getenv("TEST_OTP") or "").strip()
    if not otp:
        otp = str(data.get("otp") or "").strip()
    if not otp:
        raise ValueError(
            "No verification code configured. Use the legitimate website-issued OTP in TEST_OTP "
            "or set otp in test_data.json; do not invent or guess a code."
        )
    data["otp"] = otp
    return data


def ensure_assets() -> dict[str, Path]:
    """Create tiny valid PNG + PDF files for any upload fields (logo, licence, ID...)."""
    ASSET_DIR.mkdir(exist_ok=True)
    png = ASSET_DIR / "sample.png"
    pdf = ASSET_DIR / "sample.pdf"
    if not png.exists():
        png.write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082"))
    if not pdf.exists():
        pdf.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n")
    return {"png": png, "pdf": pdf}


def settle(page: Page, extra_ms: int = 700) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass
    page.wait_for_timeout(extra_ms)


def pick_value(d: dict, data: dict, page: Page | None = None) -> tuple[str, str]:
    hay = " ".join([d["label"], d["name"], d["id"], d["ph"], d["aria"]]).lower()
    for pattern, val in data.get("field_overrides", {}).items():
        if re.search(pattern, hay, re.I):
            return str(val), "override"
    by_type = {"email": "email", "password": "password", "tel": "phone",
               "url": "website", "date": "date", "number": "number"}
    if d["type"] in by_type:
        return str(data[by_type[d["type"]]]), by_type[d["type"]]
    for pattern, key in FIELD_RULES:
        if re.search(pattern, hay):
            return str(data[key]), key

    if page is not None:
        primary_text = " ".join(
            page.locator("button:visible, input[type=submit]:visible, [role=button]:visible")
            .evaluate_all("els => els.map(e => (e.innerText || e.getAttribute('value') || '').trim()).filter(Boolean)")
        )
        visible_input_count = page.locator(VISIBLE_FIELDS).count()
        if visible_input_count == 1 and re.search(r"\bverify\b|\bcode\b", primary_text, re.I):
            return str(data.get("otp", "")).strip() or str(data["fallback_text"]), "otp"

    return str(data["fallback_text"]), "fallback"


def mask(key: str, value: str) -> str:
    return "********" if key == "password" else value


def collect_errors(page: Page) -> list[str]:
    try:
        return page.evaluate(
            """() => { const out = new Set();
            document.querySelectorAll(
              "[role=alert],[role=status],[data-sonner-toast],.error,.text-red-500,.text-destructive,[class*=error],[id$=-message]"
            ).forEach(e => { const t = (e.innerText || '').trim(); if (t && t.length < 200) out.add(t); });
            return [...out].slice(0, 10); }""")
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Field filling
# --------------------------------------------------------------------------- #
def choose_native_select(el, value: str) -> bool:
    opts = el.evaluate("e => [...e.options].map(o => ({v: o.value, t: o.text}))")
    want = value.lower()
    match = next((o for o in opts if o["v"] and (want in o["t"].lower() or want == o["v"].lower())), None)
    match = match or next((o for o in opts if o["v"]), None)
    if not match:
        return False
    el.select_option(value=match["v"])
    return True


def choose_custom_option(page: Page, value: str) -> bool:
    page.wait_for_timeout(300)
    opts = page.get_by_role("option")
    if opts.count() == 0:
        page.keyboard.press("Escape")
        return False
    target = opts.filter(has_text=re.compile(re.escape(value), re.I))
    (target.first if target.count() else opts.first).click()
    return True


def fill_text_fields(page: Page, data: dict, step: dict) -> None:
    done: set[str] = set()
    for _ in range(3):  # re-scan: filling one field can reveal dependent fields
        progressed = False
        els = page.locator(VISIBLE_FIELDS)
        for i in range(els.count()):
            el = els.nth(i)
            try:
                d = el.evaluate(JS_DESCRIBE)
            except Exception:
                continue
            ident = f"{d['id']}|{d['name']}|{d['label']}|{d['ph']}|{i}"
            if ident in done or d["disabled"] or d["readonly"]:
                continue
            is_custom_combo = d["role"] == "combobox" and d["tag"] != "input"
            if d["tag"] in ("input", "textarea") and d["value"] and not d["role"] == "combobox":
                done.add(ident)
                continue  # already has a value (prefilled / previous pass)
            if is_custom_combo and d["text"] and not re.search(r"select|choose|^$", d["text"], re.I):
                done.add(ident)
                continue
            value, key = pick_value(d, data, page)
            ok = False
            try:
                if d["tag"] == "select":
                    ok = choose_native_select(el, value)
                elif is_custom_combo:
                    el.click()
                    ok = choose_custom_option(page, value)
                elif d["role"] == "combobox":  # searchable autocomplete input
                    el.click()
                    el.fill(value)
                    page.wait_for_timeout(400)
                    if not choose_custom_option(page, value):
                        el.press("Enter")
                    ok = True
                else:
                    el.click()
                    el.fill(value)
                    el.blur()
                    ok = True
            except Exception as exc:  # keep going; the step loop reports if the page is stuck
                step["warnings"].append(f"could not fill '{d['label'] or d['name'] or d['ph']}': {exc}".split("\n")[0])
            done.add(ident)
            if ok:
                progressed = True
                step["fields"].append({
                    "field": d["label"] or d["name"] or d["ph"] or d["id"] or d["tag"],
                    "mapped_to": key, "value": mask(key, value)})
        if not progressed:
            break


def tick_checkboxes_radios_files(page: Page, step: dict, assets: dict[str, Path]) -> None:
    # Checkboxes: tick every unchecked one (terms / consent / declarations).
    boxes = page.locator("input[type=checkbox], [role=checkbox]")
    for i in range(boxes.count()):
        cb = boxes.nth(i)
        try:
            checked = cb.evaluate("e => (e.checked !== undefined) ? e.checked : e.getAttribute('aria-checked') === 'true'")
            if checked:
                continue
            try:
                cb.check(timeout=2000)
            except Exception:
                cb.click(force=True, timeout=2000)
            step["fields"].append({"field": "checkbox", "mapped_to": "tick", "value": "checked"})
        except Exception as exc:
            step["warnings"].append(f"checkbox: {exc}".split("\n")[0])
    # Radios: select the first option of every unselected group.
    radios = page.locator("input[type=radio]")
    seen: set[str] = set()
    for i in range(radios.count()):
        r = radios.nth(i)
        try:
            name = r.get_attribute("name") or f"idx{i}"
            if name in seen:
                continue
            seen.add(name)
            if not page.locator(f"input[type=radio][name='{name}']:checked").count():
                r.check(force=True, timeout=2000)
                step["fields"].append({"field": f"radio:{name}", "mapped_to": "first option", "value": "selected"})
        except Exception as exc:
            step["warnings"].append(f"radio: {exc}".split("\n")[0])
    # File uploads (inputs are frequently hidden, so we do not require :visible).
    files = page.locator("input[type=file]")
    for i in range(files.count()):
        fi = files.nth(i)
        try:
            if fi.evaluate("e => e.files && e.files.length") > 0:
                continue
            accept = (fi.get_attribute("accept") or "").lower()
            path = assets["pdf"] if ("pdf" in accept and "image" not in accept and "png" not in accept) else assets["png"]
            fi.set_input_files(str(path))
            step["fields"].append({"field": "file upload", "mapped_to": "sample file", "value": path.name})
        except Exception as exc:
            step["warnings"].append(f"file upload: {exc}".split("\n")[0])


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #
def click_primary_button(page: Page) -> str | None:
    cands = page.locator("button:visible, input[type=submit]:visible, [role=button]:visible")
    for _ in range(4):  # button may be disabled for a moment while validation runs
        chosen = None
        for i in range(cands.count()):
            b = cands.nth(i)
            try:
                text = (b.inner_text() or b.get_attribute("value") or "").strip()
            except Exception:
                continue
            if text and NEXT_RE.match(text) and not BAD_BUTTON_RE.search(text) and b.is_enabled():
                chosen = (b, text)  # prefer the last match (primary action sits last)
        if chosen:
            chosen[0].scroll_into_view_if_needed()
            chosen[0].click()
            return chosen[1]
        page.wait_for_timeout(750)
    return None


def success_reason(page: Page) -> str | None:
    path = re.sub(r"https?://[^/]+", "", page.url)
    try:
        body = page.inner_text("body")
    except Exception:
        body = ""
    m = SUCCESS_TEXT_RE.search(body)
    if m:
        return f"success message on page: '{m.group(0)}'"
    if "register" not in path.lower() and SUCCESS_URL_RE.search(path):
        return f"redirected to {path}"
    return None


def page_signature(page: Page) -> str:
    heading = ""
    try:
        heading = page.locator("h1:visible, h2:visible, h3:visible").first.inner_text(timeout=1500)
    except Exception:
        pass
    return f"{page.url}|{heading}|{page.locator(VISIBLE_FIELDS).count()}"


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(headless: bool = True, browser_name: str = "chromium", slow_mo: int = 0, max_steps: int = 15) -> dict:
    data = load_data()
    assets = ensure_assets()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for old in REPORT_DIR.glob("*.png"):
        old.unlink()

    result = {
        "status": "FAILED", "failure_reason": "", "started": datetime.now().isoformat(timespec="seconds"),
        "email_used": data["email"], "steps": [], "failed_requests": [], "console_errors": [],
        "environment": {
            "os": platform.platform(), "python": platform.python_version(),
            "playwright": pkg_version("playwright"), "browser": browser_name,
            "headless": headless, "base_url": BASE_URL,
        },
    }
    t0 = time.time()

    with sync_playwright() as pw:
        launch_kw = {"headless": headless, "slow_mo": slow_mo}
        if os.getenv("CHROMIUM_PATH"):  # optional: use a system browser instead of Playwright's
            launch_kw["executable_path"] = os.environ["CHROMIUM_PATH"]
        if os.getenv("BROWSER_ARGS"):   # optional: e.g. "--no-sandbox" inside containers
            launch_kw["args"] = os.environ["BROWSER_ARGS"].split()
        browser = getattr(pw, browser_name).launch(**launch_kw)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        ctx.tracing.start(screenshots=True, snapshots=True)
        page = ctx.new_page()
        page.set_default_timeout(15000)
        page.on("response", lambda r: result["failed_requests"].append(f"{r.status} {r.request.method} {r.url}")
                if r.status >= 400 and "/_next/" not in r.url and "favicon" not in r.url else None)
        page.on("console", lambda m: result["console_errors"].append(m.text[:200]) if m.type == "error" else None)

        try:
            page.goto(REGISTER_URL, wait_until="domcontentloaded")
            settle(page, 1000)
            stuck = 0

            for n in range(1, max_steps + 1):
                step = {"n": n, "url": page.url, "heading": "", "fields": [], "warnings": [],
                        "clicked": None, "errors": [], "screenshot": f"step_{n:02d}.png"}
                result["steps"].append(step)
                sig = page_signature(page)
                step["heading"] = sig.split("|")[1]

                fill_text_fields(page, data, step)
                tick_checkboxes_radios_files(page, step, assets)
                page.screenshot(path=str(REPORT_DIR / step["screenshot"]), full_page=True)

                step["clicked"] = click_primary_button(page)
                if not step["clicked"]:
                    step["errors"] = collect_errors(page)
                    result["failure_reason"] = f"step {n}: no enabled Continue/Submit button found"
                    break
                settle(page)

                reason = success_reason(page)
                if reason:
                    page.screenshot(path=str(REPORT_DIR / "final.png"), full_page=True)
                    result.update(status="PASSED", failure_reason="", success_evidence=reason)
                    break

                new_sig = page_signature(page)
                step["errors"] = collect_errors(page)
                stuck = stuck + 1 if new_sig == sig else 0
                if stuck >= 2:
                    result["failure_reason"] = (f"step {n}: page did not advance after submit "
                                                f"(validation: {step['errors'] or 'none visible'})")
                    break
            else:
                result["failure_reason"] = f"flow did not finish within {max_steps} steps"
        except Exception as exc:
            result["failure_reason"] = f"{type(exc).__name__}: {exc}".split("\n")[0]
            result["traceback"] = traceback.format_exc()
        finally:
            if result["status"] != "PASSED":
                try:
                    page.screenshot(path=str(REPORT_DIR / "failure.png"), full_page=True)
                except Exception:
                    pass
            ctx.tracing.stop(path=str(REPORT_DIR / "trace.zip"))
            browser.close()

    result["duration_s"] = round(time.time() - t0, 1)
    write_reports(result, data)
    return result


def write_reports(result: dict, data: dict) -> None:
    (REPORT_DIR / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    env = result["environment"]
    lines = [
        "# Test Report - Authorized Partner signup automation", "",
        f"- **Result:** {'PASS' if result['status'] == 'PASSED' else 'FAIL'}",
        f"- **Started:** {result['started']}   **Duration:** {result['duration_s']}s",
        f"- **Target:** {env['base_url']}/register",
        f"- **Evidence:** {result.get('success_evidence') or result['failure_reason']}",
        f"- **Email used:** `{result['email_used']}`", "",
        "## Environment", "",
        f"| OS | Python | Playwright | Browser | Headless |", "|---|---|---|---|---|",
        f"| {env['os']} | {env['python']} | {env['playwright']} | {env['browser']} | {env['headless']} |", "",
        "## Steps", "",
    ]
    for s in result["steps"]:
        lines += [f"### Step {s['n']} - {s['heading'] or '(no heading)'}", f"URL: `{s['url']}`  |  Clicked: **{s['clicked']}**", ""]
        if s["fields"]:
            lines += ["| Field | Mapped to | Value |", "|---|---|---|"]
            lines += [f"| {f['field']} | {f['mapped_to']} | {f['value']} |" for f in s["fields"]]
            lines.append("")
        for w in s["warnings"]:
            lines.append(f"- warning: {w}")
        for e in s["errors"]:
            lines.append(f"- page message: {e}")
        lines += [f"![{s['screenshot']}]({s['screenshot']})", ""]
    if result["failed_requests"]:
        lines += ["## HTTP responses >= 400 seen during run", ""] + [f"- `{r}`" for r in result["failed_requests"][:25]] + [""]
    if result["console_errors"]:
        lines += ["## Browser console errors", ""] + [f"- {c}" for c in result["console_errors"][:15]] + [""]
    (REPORT_DIR / "TEST_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Automate the Authorized Partner signup flow")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--slow-mo", type=int, default=0, help="ms delay between actions")
    ap.add_argument("--browser", default="chromium", choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--max-steps", type=int, default=15)
    a = ap.parse_args()
    res = run(headless=not a.headed, browser_name=a.browser, slow_mo=a.slow_mo, max_steps=a.max_steps)
    print(f"[{res['status']}] {res.get('success_evidence') or res['failure_reason']}  "
          f"({res['duration_s']}s, {len(res['steps'])} steps)  report: reports/latest/TEST_REPORT.md")
    return 0 if res["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())

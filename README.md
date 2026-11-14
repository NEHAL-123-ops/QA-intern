# Authorized Partner - Signup Automation

End-to-end automation of the agency registration flow at
https://authorized-partner.vercel.app/register using **Python + Playwright**.
It handles every page of the multi-step wizard with no manual input and writes a test report.

## How it works
A generic *step loop* handles each wizard page:
1. Detect visible fields (label / name / placeholder / type).
2. Map each to a value in `test_data.json` (regex rules in `FIELD_RULES`).
3. Fill inputs, choose dropdown options (native and custom/Radix style), tick checkboxes,
   select radios, upload sample files.
4. Click the primary button (Continue / Next / Submit / Verify ...).
5. Stop on success (success text or redirect), or fail with the validation message if the page does not advance.

Because pages are discovered at run time, new fields or extra steps are usually handled without code changes.
For an unusual field, add a rule to `field_overrides` in `test_data.json`, e.g. `{"pan number": "123456789"}`.

## Environment
| Item | Requirement |
|------|-------------|
| OS | Windows 10/11, macOS, or Linux |
| Python | 3.10+ |
| Libraries | `playwright>=1.44`, `pytest>=8` |
| Browser | Chromium (installed by Playwright); Firefox/WebKit also supported |
| Network | Internet access to https://authorized-partner.vercel.app |

## Setup
```bash
git clone https://github.com/NEHAL-123-ops && cd authorized-partner-signup-automation
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Run
```bash
python signup_automation.py                      # headless, exit code 0 = pass
python signup_automation.py --headed --slow-mo 300   # watch it run
python signup_automation.py --browser firefox
python -m pytest -v                              # same flow via pytest
```

Optional environment variables: `BASE_URL`, `TEST_EMAIL`, `TEST_PASSWORD`, `TEST_OTP`,
`CHROMIUM_PATH` (use a system browser), `BROWSER_ARGS` (e.g. `--no-sandbox`).
The script never invents an OTP: it uses `TEST_OTP` or the value in `test_data.json`, and it raises a clear error if neither provides a real code.

## Test data
`test_data.json` - a fresh email is generated each run from `email_template`
(`qa.agent+<timestamp>@example.com`). If the site sends a real verification email/OTP,
set `TEST_EMAIL` to an inbox you control (plus-addressing works) and `TEST_OTP` to the code,
or use an email-testing service.
Note: each run submits a real registration to the live site. Test data is clearly labelled as QA data.

## Output / test report
See `TEST_REPORT.md`. Each run writes `reports/latest/` (report, JSON, screenshots, trace).

## Try it without the live site
```bash
python mock_site/serve.py &        # local 4-step wizard on :8765
BASE_URL=http://127.0.0.1:8765 python signup_automation.py
```

## Known limitations
- CAPTCHA / real email-OTP verification cannot be bypassed automatically; provide `TEST_OTP`
  or a test inbox if the live flow requires one.
- Field mapping is heuristic; unmatched required fields get `fallback_text` - add an override if validation rejects it.

## Project layout
```
signup_automation.py   main script (step loop, reporting)
test_data.json         test data and field overrides
tests/test_signup.py   pytest wrapper
mock_site/             local mock wizard used to validate the logic
reports/               generated reports (latest/ = most recent run)
.github/workflows/     optional CI run (manual or on push)
TEST_REPORT.md         test cases + how to read results
```

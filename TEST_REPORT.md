# Test Report

## Test cases

| ID | Scenario | Expected result |
|----|----------|-----------------|
| TC-01 | Open `/register`, accept Terms of Service / Privacy Policy, click **Continue** | Wizard advances to the next page |
| TC-02 | Fill every visible field on each page (text, email, phone, password + confirm, dropdowns, checkboxes, radios, uploads) | No blocking validation messages |
| TC-03 | Advance through all remaining pages (including OTP / verification page if shown) | Each click moves the wizard forward |
| TC-04 | Submit the final page | Success message or redirect (dashboard / login / pending approval / verify email) |
| TC-05 | Re-run with a fresh email (auto-generated per run) | Passes again (no duplicate-email failure) |

## Results

Every run of `python signup_automation.py` regenerates a detailed report, per-step
screenshots and a Playwright trace in **`reports/latest/`**:

- `reports/latest/TEST_REPORT.md` - result, environment, every field filled per page, HTTP errors, console errors
- `reports/latest/result.json` - machine-readable result
- `reports/latest/step_NN.png`, `final.png` / `failure.png` - screenshots
- `reports/latest/trace.zip` - open with `python -m playwright show-trace reports/latest/trace.zip`

> Run the script once and commit `reports/latest/` so the submitted report reflects your real execution.

`reports/mock_validation/` holds a run against the bundled local mock wizard
(`mock_site/`). It proves the step loop, dropdown, checkbox, upload, validation-retry
and OTP handling work. It is **not** a run against the live site.

## Defects / observations
- Passed: the flow advances from the Terms page to the profile setup page and then to the verification step.
- Failed: the script cannot complete the final OTP/verification stage without the legitimate code sent by the website to the registered email.
- Oddity on the site: the verification page shows a 6-digit email code form, but the site validates the entered value against a real server-issued code rather than a locally stored or hardcoded value. The page also shows a generic validation message (`Please Enter Valid Code!` / `Invalid OTP`) when the value is wrong or missing, which is consistent with the site requiring real email verification.
- Additional note: the site is not using a mock/static OTP; it expects a real email code, so random guesses or fallback constants are not valid verification.
- The local mock validator in `mock_site/` behaves differently and is useful only for testing the automation logic, not for proving live-site completion.

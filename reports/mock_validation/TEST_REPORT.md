# Test Report - Authorized Partner signup automation

- **Result:** PASS
- **Started:** 2026-11-14T08:10:43   **Duration:** 7.6s
- **Target:** http://127.0.0.1:8765/register
- **Evidence:** success message on page: 'Registration successful'
- **Email used:** `qa.agent+20261114081043@example.com`

## Environment

| OS | Python | Playwright | Browser | Headless |
|---|---|---|---|---|
| Linux-6.18.44-fc-v470-x86_64-with-glibc2.39 | 3.12.3 | 1.63.0 | chromium | True |

## Steps

### Step 1 - Register Your Agency
URL: `http://127.0.0.1:8765/register`  |  Clicked: **Continue**

| Field | Mapped to | Value |
|---|---|---|
| checkbox | tick | checked |

![step_01.png](step_01.png)

### Step 2 - Agency Details
URL: `http://127.0.0.1:8765/register`  |  Clicked: **Next**

| Field | Mapped to | Value |
|---|---|---|
| Agency Name | agency_name | QA Education Consultancy |
| Website | website | https://example.com |
| Country | country | Nepal |
| City | city | Kathmandu |
| file upload | sample file | sample.pdf |

![step_02.png](step_02.png)

### Step 3 - Create Account
URL: `http://127.0.0.1:8765/register`  |  Clicked: **Submit**

| Field | Mapped to | Value |
|---|---|---|
| First Name | first_name | Test |
| Last Name | last_name | Agent |
| Email | email | qa.agent+20261114081043@example.com |
| Phone | phone | 9812345678 |
| Password | password | ******** |
| Confirm Password | password | ******** |

![step_03.png](step_03.png)

### Step 4 - Verify
URL: `http://127.0.0.1:8765/register`  |  Clicked: **Verify**

| Field | Mapped to | Value |
|---|---|---|
| Verification code | otp | 123456 |

![step_04.png](step_04.png)

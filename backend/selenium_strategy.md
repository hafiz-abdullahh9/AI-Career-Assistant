# Selenium Strategy — Member 4: Web Form Automation Engine
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  

---

## 1. Overview

This document defines the complete browser automation strategy for the Web Form Automation Engine. It covers browser configuration, stealth techniques, form interaction patterns, CAPTCHA handling, anti-bot evasion, error recovery, and scaling approach.

---

## 2. Technology Decision: Selenium 4

### Why Selenium 4 (not Puppeteer / Playwright)

| Criterion | Selenium 4 | Playwright | Puppeteer |
|-----------|-----------|------------|-----------|
| Language | Python-native | Python bindings | Node.js |
| Async support | Via Celery workers | Native async | Native async |
| Grid scaling | ✅ Selenium Grid 4 | ❌ No Grid | ❌ No Grid |
| Browser support | Chrome, Firefox, Safari, Edge | Chromium, Firefox, WebKit | Chromium only |
| CDP access | ✅ BiDi + CDP | ✅ Native CDP | ✅ Native CDP |
| Community maturity | Very high | Growing | High |
| Stealth options | Via undetected-chromedriver | Via stealth JS patches | Via puppeteer-stealth |
| **Decision** | **✅ PRIMARY** | ⚠️ v2 consideration | ❌ Node.js conflict |

**Note:** The automation engine is architected behind an `AutomationDriver` abstract base class so Playwright can be swapped in as a drop-in replacement in v2 without changing business logic.

---

## 3. Browser Configuration

### 3.1 Chrome Options (Production)

```python
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc

def build_chrome_options() -> uc.ChromeOptions:
    options = uc.ChromeOptions()
    
    # === STEALTH SETTINGS ===
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # === HEADLESS (production) ===
    options.add_argument("--headless=new")           # Chrome 112+ new headless
    options.add_argument("--window-size=1920,1080")
    
    # === PERFORMANCE ===
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")          # Skip images for speed
    
    # === MEMORY ===
    options.add_argument("--memory-pressure-off")
    options.add_argument("--max_old_space_size=512")
    
    # === REALISTIC PROFILE ===
    options.add_argument("--lang=en-US,en")
    options.add_argument("--accept-lang=en-US,en;q=0.9")
    
    return options
```

### 3.2 Stealth Patches (JavaScript)

Applied via CDP after browser launch to mask automation fingerprints:

```python
STEALTH_JS_PATCHES = [
    # Remove webdriver property
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
    
    # Fake plugins array
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    """,
    
    # Fake languages
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
    """,
    
    # Chrome runtime object
    "window.chrome = { runtime: {} };",
    
    # Permissions API mock
    """
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
    );
    """,
]

async def apply_stealth_patches(driver):
    for script in STEALTH_JS_PATCHES:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": script}
        )
```

### 3.3 User-Agent Rotation

```python
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)
```

---

## 4. Selenium Grid Architecture

### 4.1 Grid Topology

```
┌─────────────────────────────────────────────────────┐
│                 Selenium Grid 4 Hub                 │
│            http://selenium-hub:4444                 │
└─────────────┬──────────────┬───────────────┬────────┘
              │              │               │
    ┌─────────▼──┐  ┌────────▼──┐  ┌────────▼──┐
    │Chrome Node │  │Chrome Node│  │Chrome Node│
    │  (Worker 1)│  │ (Worker 2)│  │ (Worker 3)│
    └────────────┘  └───────────┘  └───────────┘
```

### 4.2 Grid Configuration (docker-compose.yml excerpt)

```yaml
selenium-hub:
  image: selenium/hub:4.20.0
  ports:
    - "4444:4444"
  environment:
    - GRID_MAX_SESSION=10
    - GRID_BROWSER_TIMEOUT=60
    - GRID_SESSION_TIMEOUT=300

chrome-node:
  image: selenium/node-chrome:4.20.0
  environment:
    - SE_EVENT_BUS_HOST=selenium-hub
    - SE_NODE_MAX_SESSIONS=3
    - SE_NODE_SESSION_TIMEOUT=300
    - SE_VNC_NO_PASSWORD=1
  shm_size: "2gb"
  depends_on:
    - selenium-hub
  deploy:
    replicas: 3      # Scale this for higher throughput
```

### 4.3 Remote Driver Creation

```python
from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def create_remote_driver(grid_url: str = "http://selenium-hub:4444") -> webdriver.Remote:
    options = build_chrome_options()
    driver = webdriver.Remote(
        command_executor=grid_url,
        options=options,
    )
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(10)
    apply_stealth_patches(driver)
    return driver
```

---

## 5. Form Field Detection & Mapping Strategy

### 5.1 Field Detection Priority Order

For each form field, detect by (in order of reliability):

1. **`name` attribute** — most reliable, developer-defined
2. **`id` attribute** — reliable, often semantic
3. **`aria-label` / `aria-labelledby`** — accessibility-first forms
4. **`<label>` text** — find label, then find associated input
5. **`placeholder` text** — last resort, least reliable

### 5.2 Standard Field Mapping Table

| Our Standard Field | Common `name` values | Common `id` values | Common `aria-label` |
|-------------------|---------------------|-------------------|---------------------|
| `first_name` | first_name, firstName, fname, given_name | input-first-name | First Name |
| `last_name` | last_name, lastName, lname, family_name | input-last-name | Last Name |
| `full_name` | name, fullName, full_name | input-name | Full Name |
| `email` | email, email_address, applicant_email | input-email | Email |
| `phone` | phone, telephone, mobile, phone_number | input-phone | Phone |
| `linkedin_url` | linkedin, linkedin_url, linkedinProfile | input-linkedin | LinkedIn |
| `resume_file` | resume, cv, resume_file, attachment | input-resume | Resume |
| `cover_letter_text` | cover_letter, coverLetter, message | textarea-cover | Cover Letter |
| `work_authorization` | work_auth, authorized, visa_status | select-auth | Work Authorization |
| `years_experience` | experience, years_exp, yoe | input-experience | Years of Experience |

### 5.3 Form Field Mapper Implementation

```python
class FormFieldMapper:
    """Maps standard applicant data to form fields on any job application page."""
    
    FIELD_PATTERNS = {
        "first_name": ["first_name", "firstname", "fname", "given_name"],
        "last_name":  ["last_name", "lastname", "lname", "family_name"],
        "full_name":  ["name", "fullname", "full_name", "applicant_name"],
        "email":      ["email", "email_address", "applicant_email"],
        "phone":      ["phone", "telephone", "mobile", "phone_number"],
        "resume_file":["resume", "cv", "resume_file", "attachment", "document"],
        "cover_letter":["cover_letter", "coverletter", "message", "letter"],
        "linkedin":   ["linkedin", "linkedin_url", "linkedin_profile"],
    }
    
    def discover_fields(self, driver) -> dict:
        """Dynamically find form fields and return { our_field: WebElement }"""
        found = {}
        all_inputs = driver.find_elements(By.CSS_SELECTOR, 
            "input:not([type='hidden']):not([type='submit']), textarea, select")
        
        for element in all_inputs:
            name_val = element.get_attribute("name") or ""
            id_val   = element.get_attribute("id") or ""
            aria_val = element.get_attribute("aria-label") or ""
            combined = f"{name_val} {id_val} {aria_val}".lower()
            
            for our_field, patterns in self.FIELD_PATTERNS.items():
                if any(p in combined for p in patterns):
                    if our_field not in found:
                        found[our_field] = element
                        break
        
        return found
```

---

## 6. Human-Like Interaction Simulation

To avoid bot detection, all interactions simulate human behavior:

### 6.1 Typing Simulation

```python
import random
import time

def human_type(element, text: str, min_delay=0.05, max_delay=0.15):
    """Type text character by character with random delays."""
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(min_delay, max_delay))

def human_click(driver, element):
    """Scroll to element, pause, then click."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(random.uniform(0.3, 0.8))  # Simulate reading time
    element.click()
    time.sleep(random.uniform(0.2, 0.5))  # Simulate after-click pause
```

### 6.2 Random Delays Between Fields

```python
INTER_FIELD_DELAY = (0.3, 1.2)   # seconds between filling fields
PAGE_LOAD_PAUSE   = (1.0, 2.5)   # seconds after navigation
PRE_SUBMIT_PAUSE  = (1.5, 3.0)   # seconds before clicking submit
```

### 6.3 Mouse Movement (Optional, for higher-security sites)

```python
from selenium.webdriver.common.action_chains import ActionChains

def move_to_element_naturally(driver, element):
    """Move mouse in a curved path to element."""
    action = ActionChains(driver)
    action.move_to_element_with_offset(element, 
        random.randint(-5, 5), random.randint(-5, 5))
    action.perform()
```

---

## 7. CAPTCHA Handling Strategy

### 7.1 Detection

```python
CAPTCHA_INDICATORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "div.g-recaptcha",
    "div[class*='captcha']",
    "input[name='g-recaptcha-response']",
]

def detect_captcha(driver) -> str | None:
    """Returns captcha type or None."""
    for selector in CAPTCHA_INDICATORS:
        if driver.find_elements(By.CSS_SELECTOR, selector):
            if "recaptcha" in selector:
                return "recaptcha"
            elif "hcaptcha" in selector:
                return "hcaptcha"
            return "unknown"
    return None
```

### 7.2 Resolution Strategies

| Strategy | When to Use | Cost | Latency |
|----------|-------------|------|---------|
| **2captcha API** | Production, all captcha types | ~$1/1000 | 15–30s |
| **Anti-Captcha API** | Backup service | ~$0.80/1000 | 10–25s |
| **Manual Review Queue** | User-triggered, high-value jobs | Free | Minutes to hours |
| **Skip & Flag** | Low-value jobs, frequent captchas | Free | Instant |

### 7.3 2captcha Integration

```python
async def solve_recaptcha(site_key: str, page_url: str, api_key: str) -> str:
    """Submit captcha to 2captcha and poll for result."""
    # Step 1: Submit captcha
    submit_url = f"https://2captcha.com/in.php"
    params = {
        "key": api_key,
        "method": "userrecaptcha",
        "googlekey": site_key,
        "pageurl": page_url,
        "json": 1,
    }
    response = await http_client.post(submit_url, data=params)
    captcha_id = response.json()["request"]
    
    # Step 2: Poll for result (up to 120 seconds)
    result_url = f"https://2captcha.com/res.php"
    for _ in range(24):  # 24 * 5s = 120s max
        await asyncio.sleep(5)
        result = await http_client.get(result_url, params={
            "key": api_key, "action": "get", "id": captcha_id, "json": 1
        })
        if result.json()["status"] == 1:
            return result.json()["request"]  # The token
    
    raise CaptchaTimeoutError("Could not solve captcha in 120 seconds")
```

---

## 8. Error Recovery Strategy

### 8.1 Retry Matrix

| Error Type | Retry? | Strategy | Max Retries |
|------------|--------|----------|-------------|
| Network timeout | ✅ | Exponential backoff | 3 |
| Page load timeout | ✅ | Reload page | 2 |
| Element not found | ✅ | Wait + re-scan | 3 |
| CAPTCHA detected | ⚠️ | Solve then retry | 1 |
| Form validation error | ✅ | Fix field + resubmit | 2 |
| HTTP 4xx (page down) | ❌ | Alert, defer job | 0 |
| Browser crash | ✅ | New session | 2 |
| IP blocked | ❌ | Alert, manual review | 0 |
| Success page not found | ✅ | Re-check DOM | 2 |

### 8.2 Session Recovery

```python
class BrowserSessionManager:
    MAX_TASKS_PER_SESSION = 5    # Recycle browser after N tasks
    SESSION_TIMEOUT = 300        # 5 minutes
    
    async def get_session(self) -> webdriver.Remote:
        if self._task_count >= self.MAX_TASKS_PER_SESSION:
            await self.close_session()
        if not self._driver:
            self._driver = create_remote_driver()
            self._task_count = 0
        return self._driver
    
    async def close_session(self):
        if self._driver:
            self._driver.quit()
            self._driver = None
            self._task_count = 0
```

---

## 9. Screenshot Evidence System

### 9.1 Screenshot Capture Points

| Point | Name | Format | Required? |
|-------|------|--------|-----------|
| Page arrival | `arrival.webp` | WebP | No |
| Pre-submit | `pre_submit.webp` | WebP | Yes |
| Post-submit | `confirmation.webp` | WebP | Yes |
| Error state | `error_{timestamp}.webp` | WebP | On error |

### 9.2 Screenshot Capture

```python
async def capture_screenshot(
    driver, 
    app_id: str, 
    label: str, 
    storage_client
) -> str:
    """Capture screenshot and upload to S3. Returns storage URL."""
    png_bytes = driver.get_screenshot_as_png()
    
    # Convert to WebP for 60-70% size reduction
    img = Image.open(io.BytesIO(png_bytes))
    webp_buffer = io.BytesIO()
    img.save(webp_buffer, format="WEBP", quality=85)
    
    s3_key = f"screenshots/{app_id}/{label}_{datetime.utcnow().isoformat()}.webp"
    url = await storage_client.upload(s3_key, webp_buffer.getvalue())
    return url
```

---

## 10. Site-Specific Adapter Pattern

For high-volume platforms (LinkedIn, Indeed, Greenhouse, Lever), maintain dedicated adapters:

```
automation/
├── engine/
│   ├── base_adapter.py          # Abstract base
│   └── generic_adapter.py       # Universal DOM-based adapter
│
├── adapters/
│   ├── linkedin_adapter.py      # LinkedIn Easy Apply
│   ├── indeed_adapter.py        # Indeed Quick Apply
│   ├── greenhouse_adapter.py    # Greenhouse ATS
│   ├── lever_adapter.py         # Lever ATS
│   └── workday_adapter.py       # Workday ATS
```

Platform adapter priority:
1. Check if `application_url` matches a known platform domain → use dedicated adapter
2. Otherwise → use generic DOM-based adapter

---

## 11. Anti-Bot Detection Checklist

Before deploying:

- [ ] Selenium version hidden (via undetected-chromedriver)
- [ ] `navigator.webdriver` removed via CDP
- [ ] Realistic User-Agent set
- [ ] Plugins/languages mocked
- [ ] Human-like typing delays enabled
- [ ] Randomized inter-action pauses
- [ ] Window size is realistic (not 800x600)
- [ ] CDP `Page.addScriptToEvaluateOnNewDocument` patches applied
- [ ] No `selenium` string in browser console
- [ ] Test against bot-detection sites (bot.sannysoft.com, browserleaks.com)

---

*Next Document: `database_schema.md` — PostgreSQL schema design*

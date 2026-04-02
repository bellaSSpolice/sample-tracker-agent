# Plan: Replace Ship24 with UPS Web Scraper

> **Status:** Not started
> **Branch:** `feature/ups-scraper` (create when implementing)
> **PR Title:** Replace Ship24 API with headless UPS scraper

---

## Why

Sleepy Saturday only ships via UPS. Ship24 costs $3.90/month and supports 1,500+ carriers we don't need. We'll scrape the UPS tracking page directly using a headless browser (Selenium + Chromium), reusing the exact `driver_factory.py` pattern from the Image Creation Agent.

---

## Step-by-step Implementation

### Step 1: Create `app/tracker/driver_factory.py`

Copy from `/Users/isabellapolice/Documents/Code/Image Creation Agent/app/browser/driver_factory.py`.

Remove the `download_dir` parameter (we don't download files, just scrape). Keep everything else identical — same Chrome options, same env var pattern (`CHROME_BIN`, `CHROMEDRIVER_PATH`).

---

### Step 2: Create `app/tracker/ups_scraper.py`

New file with two things:

**Custom exception:**
```python
class UPSScraperError(Exception):
    """Raised when the UPS tracking page cannot be scraped."""
```

**Main function:**
```python
def get_ups_status(tracking_number: str) -> dict:
    """Scrape UPS tracking page for current status.

    Returns:
        {
            "status": "delivered" | "in_transit" | "out_for_delivery" | "exception" | "pending",
            "status_detail": "Delivered On Wednesday, February 11 at 9:53 A.M. at Mail Room",
            "delivered_datetime": datetime | None,
        }
    """
```

**URL format:**
```
https://www.ups.com/track?track=yes&trackNums={TRACKING_NUMBER}&loc=en_US&requester=ST/trackdetails
```

**Status detection logic** — look at text content inside `track-details-estimation`:
- Contains "Delivered" → `status = "delivered"`, parse date/time/location from `#st_App_PkgStsMonthNum` and `#st_App_PkgStsLoc`
- Contains "Out For Delivery" → `status = "out_for_delivery"`
- Contains "In Transit" → `status = "in_transit"`
- Contains "Exception" or "Delay" → `status = "exception"`
- Anything else or page fails to load → `status = "pending"`

**Error handling:**
- Page load timeout (60s) → raise `UPSScraperError` (status checker will retry next cycle)
- Element not found (page structure changed) → log warning, return `status = "pending"`
- Always quit the driver in a `finally` block

---

### Step 3: Delete Ship24 files

- **DELETE** `app/tracker/ship24_client.py`
- **DELETE** `tests/test_ship24_client.py`

---

### Step 4: Update `app/config.py`

Remove this line:
```python
# --- Ship24 ---
SHIP24_API_KEY = _clean(os.environ.get("SHIP24_API_KEY"))
```

---

### Step 5: Update `.env.example`

Remove these lines:
```
# Ship24 API
SHIP24_API_KEY=apik_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

### Step 6: Simplify `app/scanner/tracking_patterns.py`

**Before:** `CARRIER_PATTERNS` dict with USPS, UPS, FedEx, DHL, Amazon patterns + disambiguation logic + URL patterns for all carriers.

**After:** Keep ONLY the UPS pattern and UPS URL pattern. Remove all other carriers. Simplify `find_tracking_numbers()` — no disambiguation needed since there's only one carrier. The carrier is always `"UPS"`.

Keep only:
```python
CARRIER_PATTERNS = {
    "UPS": [
        re.compile(r"\b(1Z[0-9A-Z]{16})\b"),
    ],
}
```

And only the UPS URL pattern:
```python
_URL_PATTERNS = [
    (re.compile(r"https?://(?:www\.)?ups\.com/track\?.*?tracknum=([A-Za-z0-9]+)", re.IGNORECASE), "UPS"),
]
```

Remove `_CARRIER_KEYWORDS` (no disambiguation needed). Simplify `find_tracking_numbers()` to always return carrier `"UPS"`. Remove DHL special handling from `find_tracking_urls()`.

---

### Step 7: Simplify `app/scanner/email_parser.py`

No structural changes needed — the file just calls `find_tracking_numbers()` and `find_tracking_urls()` which will now only return UPS results. The carrier field will always be `"UPS"`.

No code change required here (the simplification in `tracking_patterns.py` handles it).

---

### Step 8: Update `app/scanner/scan_job.py`

**Remove these imports:**
```python
from app.tracker.ship24_client import create_tracker, Ship24Error
```

**Remove `_carrier_to_ship24_code()` function** entirely.

**In `_process_email()`**, remove the Ship24 registration block:
```python
# DELETE this block:
ship24_tracker_id = None
courier_code = _carrier_to_ship24_code(carrier)
try:
    tracker = create_tracker(tracking_number, courier_code)
    ship24_tracker_id = tracker.get("trackerId")
except Ship24Error:
    logger.warning(...)
```

**In the `TrackedShipment(...)` constructor**, remove `ship24_tracker_id=ship24_tracker_id`. Since we scrape on-demand by tracking number, no registration step is needed.

**Hardcode carrier to "UPS":**
```python
carrier = "UPS"  # Sleepy Saturday ships UPS only
```

**Update docstring** to reflect: scan email → find UPS tracking number → match → store (no API registration step).

---

### Step 9: Update `app/tracker/status_checker.py`

**Replace imports:**
```python
# OLD:
from app.tracker.ship24_client import get_tracking_results, normalize_status, Ship24Error

# NEW:
from app.tracker.ups_scraper import get_ups_status, UPSScraperError
```

**Update `run_status_check()`:**
- Change the query filter: instead of `TrackedShipment.ship24_tracker_id.isnot(None)`, just filter by `TrackedShipment.current_status != "delivered"` (all shipments are scrapable by tracking number).

**Rewrite `_check_shipment()`:**
```python
def _check_shipment(session, shipment):
    try:
        result = get_ups_status(shipment.tracking_number)
    except UPSScraperError:
        logger.warning("Failed to scrape status for %s, will retry next cycle", shipment.tracking_number)
        return

    new_status = result["status"]
    old_status = shipment.current_status

    shipment.current_status = new_status
    shipment.status_detail = result.get("status_detail", "")
    shipment.last_checked_at = datetime.now(timezone.utc)
    shipment.updated_at = datetime.now(timezone.utc)

    if new_status != old_status:
        logger.info("Status changed for %s: %s -> %s", shipment.tracking_number, old_status, new_status)

    if new_status == "delivered" and old_status != "delivered":
        if result.get("delivered_datetime"):
            shipment.delivered_datetime = result["delivered_datetime"]
        _handle_delivery(session, shipment)

    if new_status == "exception" and not shipment.issue_draft_created:
        _handle_exception(session, shipment, result.get("status_detail", ""))

    session.add(shipment)
    session.commit()
```

**`_handle_delivery()` and `_handle_exception()`** stay the same — no changes needed.

**Update docstring** to say "scrape UPS" instead of "check Ship24".

---

### Step 10: Update `app/db/models.py`

Rename `ship24_tracker_id` column to `scraper_note`:
```python
# OLD:
ship24_tracker_id = Column(String(100))

# NEW:
scraper_note = Column(String(100))
```

This column was used to store the Ship24 tracker UUID. Now it's unused, but we keep it as a nullable text field in case we want to store scraper metadata later. The DB migration handles the actual rename.

---

### Step 11: Create `app/db/migrations/003_rename_ship24_column.sql`

```sql
ALTER TABLE tracked_shipments
    RENAME COLUMN ship24_tracker_id TO scraper_note;
```

---

### Step 12: Update `app/scheduler/jobs.py`

Change the job name string:
```python
# OLD:
name="Check Ship24 for delivery updates",

# NEW:
name="Check UPS for delivery updates",
```

---

### Step 13: Update `Dockerfile`

Add Chromium installation (copy from Image Creation Agent Dockerfile):

```dockerfile
FROM python:3.12-slim

# Install Chromium and its WebDriver
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Tell Selenium where to find Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Gunicorn with 1 worker (critical — APScheduler needs single process)
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 "app:create_app()"
```

---

### Step 14: Update `requirements.txt`

```
# Web framework
Flask==2.3.3
gunicorn==21.2.0

# Database
SQLAlchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.13.1

# Gmail API
google-api-python-client==2.108.0
google-auth-httplib2==0.2.0
google-auth-oauthlib==1.2.0

# UPS tracking (headless browser)
selenium==4.27.1
requests==2.31.0

# Scheduling
APScheduler==3.10.4

# HTML parsing
beautifulsoup4==4.12.2

# Testing
pytest==7.4.4
pytest-mock==3.12.0

# Utilities
python-dotenv==1.0.0
```

Changes: added `selenium==4.27.1`, changed comment from "Ship24 API" to "UPS tracking (headless browser)".

---

### Step 15: Update `tests/conftest.py`

Remove `SHIP24_API_KEY` from the env setup:
```python
# DELETE this line:
os.environ.setdefault("SHIP24_API_KEY", "test-api-key")
```

Update `sample_shipment` fixture — change `ship24_tracker_id` to `scraper_note`:
```python
# OLD:
shipment.ship24_tracker_id = "tracker-abc-123"

# NEW:
shipment.scraper_note = None
```

---

### Step 16: Create `tests/test_ups_scraper.py`

Replace `tests/test_ship24_client.py` with UPS scraper tests. All Selenium calls are mocked.

Test cases:
1. **Happy path: delivered status** — mock page with "Delivered" text → returns `{"status": "delivered", ...}`
2. **In transit status** — mock page with "In Transit" text → returns `{"status": "in_transit", ...}`
3. **Out for delivery** — mock page with "Out For Delivery" → returns `{"status": "out_for_delivery", ...}`
4. **Exception/delay** — mock page with "Exception" → returns `{"status": "exception", ...}`
5. **Page timeout** — mock driver to raise timeout → raises `UPSScraperError`
6. **Element not found** — mock page with no status elements → returns `{"status": "pending", ...}`
7. **Driver always quit** — verify `driver.quit()` is called even on error (via `finally`)

---

### Step 17: Simplify `tests/test_tracking_patterns.py`

- Remove `TestUSPS`, `TestFedEx`, `TestDHL`, `TestAmazon` classes
- Keep `TestUPS` class
- Update `TestCarrierPatternsExposed.test_all_five_carriers_present` → only `"UPS"` expected
- Remove USPS/FedEx/DHL URL tests from `TestTrackingURLs`, keep UPS URL test
- Keep `TestNegativeCases` and `TestMultipleNumbers` (update to UPS-only examples)
- Remove `TestDisambiguation` (no longer relevant with one carrier)

---

### Step 18: Update `tests/test_email_parser.py`

- Change `TestRealisticUSPSEmail` → `TestRealisticUPSEmail` with a UPS tracking number (1Z...)
- Update `TestHTMLOnlyEmail` to use a UPS number instead of FedEx
- Update `TestTrackingURLInHref` to use a UPS URL
- Update `TestMultipleDifferentNumbers` → test two different UPS tracking numbers instead of UPS + USPS
- `TestNoTrackingNumber` and `TestDeduplication` stay the same (already use UPS or are carrier-agnostic)

---

### Step 19: Update `tests/test_scan_job.py`

- Remove `@patch("app.scanner.scan_job.create_tracker")` from all tests
- Remove `mock_create_tracker` parameter and assertions
- Remove `test_scan_handles_ship24_failure` entirely (no more Ship24)
- Update `mock_gmail_emails` fixture: change USPS tracking number to a UPS 1Z number
- In `test_scan_finds_tracking_in_email`: remove `mock_create_tracker.assert_called_once()` check

---

### Step 20: Update `tests/test_status_checker.py`

- Change all `@patch("app.tracker.status_checker.get_tracking_results")` → `@patch("app.tracker.status_checker.get_ups_status")`
- Update mock return values: instead of Ship24's nested `{"trackings": [{...}]}` format, use the flat dict: `{"status": "delivered", "status_detail": "...", "delivered_datetime": ...}`
- Change `_make_shipment()`: rename `tracker_id` param → remove it, rename `ship24_tracker_id` → `scraper_note = None`
- Rename `test_ship24_failure_skips_shipment` → `test_scraper_failure_skips_shipment`, use `UPSScraperError` instead of `Ship24Error`
- Remove `test_empty_tracking_data_handled` (scraper returns a status dict, never empty trackings list)
- Add new test: `test_scraper_returns_pending_no_crash` — scraper returns `{"status": "pending", ...}` → shipment stays pending

---

### Step 21: Update `tests/test_end_to_end.py`

**Scan phase test:**
- Remove `@patch("app.scanner.scan_job.create_tracker")` and `mock_create_tracker` parameter
- Remove `mock_create_tracker.assert_called_once_with(...)` assertion
- Change tracking number from USPS (`9400...`) to UPS (`1Z...`)
- Change carrier assertions from `"USPS"` to `"UPS"`

**Delivery phase test:**
- Change `@patch("app.tracker.status_checker.get_tracking_results")` → `@patch("app.tracker.status_checker.get_ups_status")`
- Update mock return from Ship24 format to scraper format: `{"status": "delivered", "status_detail": "...", "delivered_datetime": datetime(...)}`
- Change `ship24_tracker_id` → `scraper_note = None` in mock shipment
- Change carrier from `"USPS"` to `"UPS"`

---

## Files Summary

| Action | File |
|--------|------|
| CREATE | `app/tracker/driver_factory.py` |
| CREATE | `app/tracker/ups_scraper.py` |
| CREATE | `app/db/migrations/003_rename_ship24_column.sql` |
| CREATE | `tests/test_ups_scraper.py` |
| DELETE | `app/tracker/ship24_client.py` |
| DELETE | `tests/test_ship24_client.py` |
| EDIT | `app/config.py` |
| EDIT | `.env.example` |
| EDIT | `app/scanner/tracking_patterns.py` |
| EDIT | `app/scanner/scan_job.py` |
| EDIT | `app/tracker/status_checker.py` |
| EDIT | `app/db/models.py` |
| EDIT | `app/scheduler/jobs.py` |
| EDIT | `Dockerfile` |
| EDIT | `requirements.txt` |
| EDIT | `tests/conftest.py` |
| EDIT | `tests/test_tracking_patterns.py` |
| EDIT | `tests/test_email_parser.py` |
| EDIT | `tests/test_scan_job.py` |
| EDIT | `tests/test_status_checker.py` |
| EDIT | `tests/test_end_to_end.py` |

No changes needed: `app/scanner/email_parser.py` (simplification happens upstream in `tracking_patterns.py`)

---

## How to Resume

1. Open Claude Code in the `sample tracker agent` directory
2. Say: "Implement the plan in `PLAN-replace-ship24-with-ups-scraper.md`"
3. Claude will follow each step in order
4. After all changes, run `python3 -m pytest tests/ --tb=short` to verify
5. Delete this plan file before merging

from __future__ import annotations

import logging
import subprocess
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


logger = logging.getLogger("vu_buddy.lms_login")


def _cleanup_zombie_chrome() -> None:
    """Kill only orphaned chromedriver processes, NOT the user's Chrome."""
    for proc in ("chromedriver", "chromedriver.exe"):
        try:
            subprocess.run(["taskkill", "/f", "/im", proc], capture_output=True, timeout=5)
        except Exception:
            pass


def _build_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()

    # Hide automation so VULMS can't detect headless Chrome
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # Remove the automation flag from navigator
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    # Hide the webdriver property that bot-detection scripts check
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """
        },
    )

    return driver


def _find_login_fields(driver: webdriver.Chrome) -> tuple[object, object, object]:
    """
    Find username, password inputs and submit button on VULMS login page.
    Tries multiple strategies because VULMS markup changes periodically.
    """
    wait = WebDriverWait(driver, 15)
    body_text = driver.find_element(By.TAG_NAME, "body").text.lower()

    logger.info("Login page body snippet: %s", body_text[:200])

    # ----- Strategy 1: look for a dedicated login form container -----
    form_selectors = [
        "form#form1",
        "form[name='aspnetForm']",
        "form",
        "#login",
        ".login",
        "#loginForm",
    ]
    form = None
    for sel in form_selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, sel)
        if elements:
            form = elements[0]
            break

    # ----- Strategy 2: find text input and password input -----
    user_input = None
    pass_input = None

    # Try by placeholder first (most reliable for VULMS)
    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email'], input:not([type])"):
        ph = (inp.get_attribute("placeholder") or "").lower()
        name = (inp.get_attribute("name") or "").lower()
        inp_id = (inp.get_attribute("id") or "").lower()
        if "student" in ph or "user" in ph or "id" in ph or "user" in name or "id" in name:
            user_input = inp
            break

    if not user_input:
        # Fallback: first visible text input
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input:not([type])"):
            if inp.is_displayed():
                user_input = inp
                break

    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
        ph = (inp.get_attribute("placeholder") or "").lower()
        name = (inp.get_attribute("name") or "").lower()
        inp_id = (inp.get_attribute("id") or "").lower()
        if "password" in ph or "pass" in name or "pass" in inp_id:
            pass_input = inp
            break

    if not pass_input:
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
            if inp.is_displayed():
                pass_input = inp
                break

    # ----- Strategy 3: find submit button -----
    submit_button = None
    for btn in driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], button"):
        btn_text = (btn.text or "").lower()
        btn_val = (btn.get_attribute("value") or "").lower()
        btn_id = (btn.get_attribute("id") or "").lower()
        if "login" in btn_text or "sign" in btn_text or "login" in btn_val or "login" in btn_id or "submit" in btn_id:
            submit_button = btn
            break

    if not submit_button:
        buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        if buttons:
            submit_button = buttons[0]

    return user_input, pass_input, submit_button


def login_to_lms(student_id: str, password: str, *, lms_url: str = "https://vulms.vu.edu.pk") -> webdriver.Chrome:
    """
    Log in to VULMS and return a Selenium driver with an authenticated session.
    """
    if not student_id or not password:
        raise ValueError("Missing LMS credentials. Set LMS_ID and LMS_PASSWORD in .env.")

    driver = _build_driver()

    try:
        logger.info("Opening LMS login page: %s", lms_url)
        driver.get(lms_url)
        time.sleep(3)

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        user_input, pass_input, submit_button = _find_login_fields(driver)

        if not user_input or not pass_input:
            # Dump the page HTML for debugging
            html = driver.page_source[:2000]
            logger.error("Could not find login inputs. Page HTML snippet: %s", html)
            raise RuntimeError("Could not locate login fields on VULMS page.")

        user_input.clear()
        user_input.send_keys(student_id)
        time.sleep(0.5)
        pass_input.clear()
        pass_input.send_keys(password)
        time.sleep(0.5)

        if submit_button:
            logger.info("Clicking login button.")
            submit_button.click()
        else:
            logger.info("No submit button found, pressing Enter on password field.")
            pass_input.submit()

        time.sleep(5)

        # Wait until we leave the login page
        try:
            WebDriverWait(driver, 35).until(lambda d: "login" not in d.current_url.lower())
            logger.info("Login successful. Current URL: %s", driver.current_url)
        except TimeoutException:
            # Check if we actually logged in despite URL
            current_url = driver.current_url.lower()
            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            logger.warning(
                "URL still contains 'login'. URL=%s body_preview=%s",
                current_url,
                page_text[:200],
            )
            if "login" in current_url and ("invalid" in page_text or "error" in page_text):
                raise RuntimeError("Login failed: invalid credentials or page error.")
            # Might still be on a post-login page that happens to have 'login' in URL
            logger.info("Proceeding anyway — possible post-login page.")

        return driver

    except (TimeoutException, WebDriverException) as exc:
        logger.exception("Login failed.")
        try:
            driver.quit()
        except Exception:
            pass
        raise RuntimeError("Failed to login to LMS. Check credentials/selectors.") from exc

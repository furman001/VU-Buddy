import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


logger = logging.getLogger("vu_buddy.login")


def _build_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    return webdriver.Chrome(options=options)


def login_to_lms(lms_url: str, username: str, password: str) -> webdriver.Chrome:
    """
    Login to VULMS and return authenticated Selenium driver session.
    """
    logger.info("Launching headless Chrome...")
    driver = _build_driver()
    wait = WebDriverWait(driver, 25)

    try:
        logger.info("Opening LMS login page...")
        driver.get(lms_url)

        # VULMS login field IDs can vary, so try common selectors safely.
        user_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[name*='user'], input[id*='user']"))
        )
        pass_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], input[name*='pass'], input[id*='pass']"))
        )

        user_input.clear()
        user_input.send_keys(username)
        pass_input.clear()
        pass_input.send_keys(password)

        submit_buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        if submit_buttons:
            submit_buttons[0].click()
        else:
            pass_input.submit()

        # Delay handling after login: wait for body to stabilize or URL change.
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        WebDriverWait(driver, 20).until(lambda d: d.current_url != lms_url or "login" not in d.current_url.lower())
        logger.info("Login successful.")
        return driver

    except (TimeoutException, WebDriverException) as exc:
        logger.exception("Login failed.")
        driver.quit()
        raise RuntimeError("Failed to login to LMS. Check credentials/selectors.") from exc

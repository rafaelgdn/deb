from selenium_driverless import webdriver
from selenium_driverless.types.webelement import StaleElementReferenceException
import os
import time
import shutil
import random
import asyncio


def setup_temp_profile():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    current_dir_abspath = os.path.abspath(current_dir)
    root_dir = os.path.join(current_dir_abspath, "..")
    root_dir_abspath = os.path.abspath(root_dir)

    profiles_dir = os.path.join(root_dir_abspath, "utils", "profiles")
    temp_dir = os.path.join(root_dir_abspath, "profiles_temp")
    temp_dir_abspath = os.path.abspath(temp_dir)

    profile_name = "Profile 5"

    if os.path.exists(temp_dir_abspath):
        try:
            shutil.rmtree(temp_dir_abspath)
            print("Temp folder successfully removed.")
        except Exception as e:
            print(f"Error removing temp folder: {e}")

    os.makedirs(temp_dir_abspath, exist_ok=True)

    source_profile = os.path.join(profiles_dir, profile_name)
    dest_profile = os.path.join(temp_dir_abspath, profile_name)

    if os.path.exists(dest_profile):
        shutil.rmtree(dest_profile)

    shutil.copytree(source_profile, dest_profile)
    return temp_dir_abspath, profile_name


async def start_driver(downloads_dir=None):
    temp_dir_abspath, profile_name = setup_temp_profile()

    options = webdriver.ChromeOptions()
    options.downloads_dir = downloads_dir
    options.user_data_dir = temp_dir_abspath
    options.add_argument(f"--user-data-dir={temp_dir_abspath}")
    options.add_argument(f"--profile-directory={profile_name}")
    options.add_argument("--window-size=1920,1080")
    # options.add_argument("--headless")  # uncomment this line to run in headless mode
    options.add_argument("--disable-gpu")  # comment to run in a cloud
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")
    options.add_argument("--disable-features=BlockInsecurePrivateNetworkRequests")
    options.add_argument("--disable-features=OutOfBlinkCors")
    options.add_argument("--disable-features=SameSiteByDefaultCookies,CookiesWithoutSameSiteMustBeSecure")
    options.add_argument("--disable-features=CrossSiteDocumentBlockingIfIsolating,CrossSiteDocumentBlockingAlways")
    options.add_argument(
        "--disable-features=ImprovedCookieControls,LaxSameSiteCookies,SameSiteByDefaultCookies,CookiesWithoutSameSiteMustBeSecure"
    )
    options.add_argument("--disable-features=SameSiteDefaultChecksMethodRigorously")
    driver = await webdriver.Chrome(options=options)
    return driver


async def move_mouse_around_element(driver, element, num_movements=6):
    location = await element.location
    size = await element.size
    pointer = driver.current_pointer

    x_min = max(0, location["x"] - 200)
    x_max = location["x"] + size["width"] + 200
    y_min = max(0, location["y"] - 200)
    y_max = location["y"] + size["height"] + 200

    for _ in range(num_movements):
        x = random.randint(x_min, x_max)
        y = random.randint(y_min, y_max)
        await pointer.move_to(x, y, smooth_soft=60, total_time=random.uniform(0.3, 0.7))

    center_x = location["x"] + size["width"] // 2
    center_y = location["y"] + size["height"] // 2
    await pointer.move_to(center_x, center_y, smooth_soft=60, total_time=0.5)


async def type_with_delay(driver, element, text, min_delay=0.2, max_delay=0.5):
    for i, char in enumerate(text):
        if i == 0:
            await element.send_keys(char, click_on=True)
        else:
            await element.send_keys(char, click_on=False)

        if i < len(text) - 1:
            await driver.sleep(random.uniform(min_delay, max_delay))

    await driver.sleep(0.5)


async def wait_for_element(driver, by, CSS, timeout=30):
    start_time = time.time()

    while True:
        try:
            element = await driver.find_elements(by, CSS)
            if element:
                return element
            elif time.time() - start_time > timeout:
                raise TimeoutError(f"Element with {by}={CSS} not found within {timeout} seconds")
        except StaleElementReferenceException:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Element with {by}={CSS} not found within {timeout} seconds")


async def get_element_details(driver, element):
    attributes = await driver.execute_script(
        """
            var items = {};
            for (index = 0; index < arguments[0].attributes.length; ++index) {
                items[arguments[0].attributes[index].name] = arguments[0].attributes[index].value
            };
            return items;
        """,
        element,
    )

    properties = await driver.execute_script(
        """
            var props = {};
            var element = arguments[0];
            props['tagName'] = element.tagName;
            props['text'] = element.textContent;
            props['isDisplayed'] = element.offsetParent !== null;
            props['isEnabled'] = !element.disabled;
            return props;
        """,
        element,
    )

    details = {**attributes, **properties}
    return details


async def race(*coroutines):
    done, pending = await asyncio.wait(coroutines, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    return done.pop().result()

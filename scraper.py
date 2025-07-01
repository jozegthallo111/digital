import time
import csv
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from tqdm import tqdm
import os

# Constants
WAIT_TIMEOUT = 25  # seconds
MAX_RETRIES = 3
REQUEST_DELAY = (2, 5)  # Random delay between requests
SAVE_EVERY = 25  # Save data every 25 cards

CATEGORY_INFO = {
    "pokemon": {
        "start_url": "https://www.pricecharting.com/category/pokemon-cards",
        "csv_file": "pokemon_cards.csv",
        "set_filter": "pokemon"
    },
    "yugioh": {
        "start_url": "https://www.pricecharting.com/category/yugioh-cards",
        "csv_file": "yugioh_cards.csv",
        "set_filter": "yugioh"
    }
}

def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def slow_scroll(driver):
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_attempts = 0
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(2.5, 4.0))
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            scroll_attempts += 1
            if scroll_attempts > 2:
                break
        else:
            scroll_attempts = 0
            last_height = new_height

def load_scraped_urls(csv_path):
    scraped_urls = set()
    if os.path.exists(csv_path):
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                url = row.get("Card URL", "").strip()
                if url:
                    scraped_urls.add(url)
    return scraped_urls

def save_data(data, filename):
    if not data:
        return
    try:
        file_exists = os.path.isfile(filename)
        with open(filename, 'a', newline='', encoding='utf-8') as f:
            keys = data[0].keys()
            writer = csv.DictWriter(f, fieldnames=keys)
            if not file_exists:
                writer.writeheader()
            writer.writerows(data)
        print(f"Saved {len(data)} cards to {filename}")
    except Exception as e:
        print(f"Error saving data: {e}")

def scrape_card_data(driver, card_url):
    for attempt in range(MAX_RETRIES):
        try:
            driver.get(card_url)
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1#product_name"))
            )
            name = driver.find_element(By.CSS_SELECTOR, "h1#product_name").text.strip()

            prices = []
            volumes = []

            price_elements = driver.find_elements(By.CSS_SELECTOR, "span.price.js-price")
            for elem in price_elements:
                prices.append(elem.text.strip())

            volume_elements = driver.find_elements(By.CSS_SELECTOR, "td.js-show-tab")
            for elem in volume_elements:
                volumes.append(elem.text.replace("volume:", "").strip())

            rarity = "N/A"
            model_number = "N/A"
            img_url = "N/A"

            try:
                rarity = driver.find_element(By.CSS_SELECTOR, "td.details[itemprop='description']").text.strip()
            except NoSuchElementException:
                pass

            try:
                model_number = driver.find_element(By.CSS_SELECTOR, "td.details[itemprop='model-number']").text.strip()
            except NoSuchElementException:
                pass

            try:
                img = driver.find_element(By.CSS_SELECTOR, "img[src*='1600.jpg']")
                img_url = img.get_attribute("src")
            except NoSuchElementException:
                pass

            while len(prices) < 6:
                prices.append("N/A")
            while len(volumes) < 6:
                volumes.append("N/A")

            return {
                "Name": name,
                "Raw Price": prices[0],
                "Raw Volume": volumes[0],
                "Grade 7": prices[1],
                "Grade 7 Volume": volumes[1],
                "Grade 8": prices[2],
                "Grade 8 Volume": volumes[2],
                "Grade 9": prices[3],
                "Grade 9 Volume": volumes[3],
                "Grade 9.5": prices[4],
                "Grade 9.5 Volume": volumes[4],
                "PSA 10": prices[5],
                "PSA 10 Volume": volumes[5],
                "Rarity": rarity,
                "Model Number": model_number,
                "Image URL": img_url,
                "Card URL": card_url,
            }

        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {card_url}: {str(e)}")
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(5)

def get_all_set_urls(driver, start_url, filter_keyword):
    driver.get(start_url)
    time.sleep(random.uniform(*REQUEST_DELAY))
    WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/console/']"))
    )
    slow_scroll(driver)
    set_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/console/']")

    urls = []
    for link in set_links:
        url = link.get_attribute("href")
        name = link.text.strip().lower()

        # Filter sets that include the filter_keyword in name or url
        if filter_keyword in url.lower() or filter_keyword in name:
            urls.append(url)

    urls = list(set(urls))  # Remove duplicates
    print(f"Found {len(urls)} sets for {filter_keyword}")
    return urls

def get_card_urls_in_set(driver, set_url):
    driver.get(set_url)
    time.sleep(random.uniform(*REQUEST_DELAY))
    try:
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "td.title a"))
        )
    except TimeoutException:
        print(f"Timeout waiting for card links on set page: {set_url}")
        return []
    slow_scroll(driver)

    card_links = driver.find_elements(By.CSS_SELECTOR, "td.title a")
    card_urls = [elem.get_attribute("href") for elem in card_links if elem.get_attribute("href")]
    card_urls = list(set(card_urls))  # Remove duplicates
    return card_urls

def scrape_category(driver, category_name):
    info = CATEGORY_INFO[category_name]
    csv_file = info["csv_file"]
    filter_keyword = info["set_filter"]

    scraped_urls = load_scraped_urls(csv_file)
    all_data = []

    set_urls = get_all_set_urls(driver, info["start_url"], filter_keyword)
    if not set_urls:
        print(f"No sets found for {category_name}. Exiting.")
        return

    for set_url in tqdm(set_urls, desc=f"Sets in {category_name}", unit="set"):
        print(f"Processing set: {set_url.split('/')[-1]}")

        # Get all card URLs in this set first
        card_urls = get_card_urls_in_set(driver, set_url)
        if not card_urls:
            print(f"No cards found in set {set_url}. Skipping.")
            continue

        for card_url in tqdm(card_urls, desc=f"Cards in set {set_url.split('/')[-1]}", unit="card", leave=False):
            if not card_url or card_url in scraped_urls:
                continue

            card_data = scrape_card_data(driver, card_url)
            if card_data:
                all_data.append(card_data)
                scraped_urls.add(card_url)

            if len(all_data) >= SAVE_EVERY:
                save_data(all_data, csv_file)
                all_data = []

            time.sleep(random.uniform(*REQUEST_DELAY))

    # Save any leftover data
    if all_data:
        save_data(all_data, csv_file)

def main():
    driver = create_driver()
    try:
        scrape_category(driver, "pokemon")
        scrape_category(driver, "yugioh")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

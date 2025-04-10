import os
import json
import re
import time
from time import sleep
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from flask import Flask, request, jsonify, send_from_directory
from threading import Thread
from flask_cors import CORS
from flask import Flask, request, jsonify, send_from_directory
import platform
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()])
logger = logging.getLogger("linkedin-scraper")

app = Flask(__name__, static_folder="static")
CORS(app)  # Enable CORS for all routes

# Global variables to store state
driver = None
is_logged_in = False
is_scraping = False
current_job = None
job_results = {}
cookies_jar = None  # Store LinkedIn cookies here

def setup_driver(headless=False):
    """Set up and return a WebDriver instance for any available browser"""
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    import platform
    
    system = platform.system()  # Windows, Darwin (macOS), or Linux
    logger.info(f"Detected operating system: {system}")

    # Set common arguments
    browser_options = {
        "window_size": "--window-size=1366,768",
        "no_sandbox": "--no-sandbox",
        "disable_dev_shm": "--disable-dev-shm-usage",
        "headless": "--headless" if headless else None,
        "disable_gpu": "--disable-gpu" if headless else None
    }
    
    # List of browsers to try, in order of preference
    browsers = ["chrome", "firefox", "edge", "safari"]
    
    # If on Windows, prioritize Edge
    if system == "Windows":
        browsers = ["edge", "chrome", "firefox"]
    # If on macOS, include Safari
    elif system == "Darwin":
        browsers = ["chrome", "safari", "firefox", "edge"]
    
    for browser_name in browsers:
        try:
            logger.info(f"Attempting to use {browser_name.capitalize()} browser...")
            
            if browser_name == "chrome":
                options = webdriver.ChromeOptions()
                for arg in browser_options.values():
                    if arg:
                        options.add_argument(arg)
                driver = webdriver.Chrome(options=options)
            
            elif browser_name == "firefox":
                options = webdriver.FirefoxOptions()
                if browser_options["headless"]:
                    options.add_argument("-headless")
                driver = webdriver.Firefox(options=options)
            
            elif browser_name == "edge":
                options = webdriver.EdgeOptions()
                for arg in browser_options.values():
                    if arg:
                        options.add_argument(arg)
                driver = webdriver.Edge(options=options)
            
            elif browser_name == "safari" and system == "Darwin":
                # Safari doesn't support headless mode
                driver = webdriver.Safari()
            
            else:
                continue  # Skip unsupported browsers
            
            logger.info(f"Successfully initialized {browser_name.capitalize()} browser")
            return driver
        
        except (WebDriverException, Exception) as e:
            logger.error(f"{browser_name.capitalize()} browser not available: {e}")
    
    # If we get here, no browser was available
    raise Exception("No compatible browser found. Please ensure Chrome, Firefox, Edge, or Safari is installed with the corresponding WebDriver.")

def switch_to_headless():
    """Switch the current visible Chrome driver to headless mode"""
    global driver, is_logged_in
    
    if not driver or not is_logged_in:
        logger.warning("No active driver to switch to headless mode")
        return False
    
    try:
        # Get the current cookies from the visible browser
        cookies = driver.get_cookies()
        current_url = driver.current_url
        
        logger.info("Switching to headless mode...")
        
        # Save the current window handle to restore later if needed
        original_window = driver.current_window_handle
        
        # Create a new headless driver
        headless_driver = setup_driver(headless=True)
        
        # Navigate to LinkedIn
        headless_driver.get("https://www.linkedin.com")
        
        # Add all cookies to maintain the session
        for cookie in cookies:
            # Some cookies might cause issues, so we'll try to add each one individually
            try:
                headless_driver.add_cookie(cookie)
            except Exception as e:
                logger.warning(f"Could not add cookie {cookie.get('name')}: {e}")
        
        # Navigate to the same page the user was on
        headless_driver.get(current_url)
        sleep(2)
        
        # Verify we're still logged in
        if "feed" in headless_driver.current_url or not headless_driver.find_elements(By.ID, 'username'):
            logger.info("Successfully switched to headless mode while maintaining login session")
            
            # Close the original visible browser
            driver.quit()
            
            # Update the global driver instance
            driver = headless_driver
            return True
        else:
            logger.error("Failed to maintain login session in headless mode")
            headless_driver.quit()
            return False
    except Exception as e:
        logger.error(f"Error switching to headless mode: {e}")
        return False

def cookie_login():
    """Log in using cookies previously obtained from the user"""
    global driver, is_logged_in, cookies_jar
    
    if not cookies_jar:
        logger.error("No cookies available to use for login")
        return False
    
    try:
        logger.info("Attempting to log in using cookies...")
        
        # Create a new headless driver
        driver = setup_driver(headless=True)
        
        # Navigate to LinkedIn
        driver.get("https://www.linkedin.com")
        
        # Add all cookies
        for cookie in cookies_jar:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.warning(f"Could not add cookie {cookie.get('name')}: {e}")
        
        # Navigate to the feed to verify login
        driver.get("https://www.linkedin.com/feed/")
        sleep(2)
        
        # Verify we're logged in
        if "feed" in driver.current_url or not driver.find_elements(By.ID, 'username'):
            logger.info("Successfully logged in with cookies")
            is_logged_in = True
            return True
        else:
            logger.error("Cookie login failed - session may have expired")
            if driver:
                driver.quit()
                driver = None
            return False
    except Exception as e:
        logger.error(f"Error during cookie login: {e}")
        return False

def manual_login():
    """Present a browser window for the user to manually log in to LinkedIn with verification guidance"""
    global driver, is_logged_in
    
    logger.info("\n" + "="*80)
    logger.info("STARTING LINKEDIN MANUAL LOGIN PROCESS")
    logger.info("="*80)
    
    logger.info("Opening browser for manual login...")
    
    # Create a visible browser window
    driver = setup_driver(headless=False)
    driver.get('https://www.linkedin.com/login')
    logger.info(f"Current page title: {driver.title}")
    
    # Display clear instructions for the user
    logger.info("\n📱 LINKEDIN LOGIN & VERIFICATION GUIDE 📱")
    logger.info("1. Enter your LinkedIn credentials in the browser window that just opened.")
    logger.info("2. LinkedIn may ask for additional verification via:")
    logger.info("   - Email code")
    logger.info("   - SMS code")
    logger.info("   - LinkedIn mobile app approval")
    logger.info("3. Complete ALL verification steps until you see your LinkedIn feed.")
    logger.info("4. DO NOT close the browser window.")
    
    # Wait for user confirmation before proceeding
    logger.info("\n⚠️ IMPORTANT: DO NOT CONTINUE UNTIL VERIFICATION IS COMPLETE ⚠️")
    
    # Wait for the user to log in manually (up to 5 minutes)
    wait_time = 0
    max_wait_time = 300  # 5 minutes
    check_interval = 3  # Check every 3 seconds
    verification_warning_shown = False
    
    while wait_time < max_wait_time:
        # Check if we're logged in
        try:
            current_url = driver.current_url
            logger.info(f"Current URL: {current_url}")
            
            # Look for verification indicators in the URL or page
            if "checkpoint" in current_url or "challenge" in current_url or "verify" in current_url:
                if not verification_warning_shown:
                    logger.info("\n🔐 VERIFICATION DETECTED 🔐")
                    logger.info("LinkedIn is asking for additional verification.")
                    logger.info("Please complete the verification process in the browser window.")
                    verification_warning_shown = True
                    
                # Show timer for verification
                logger.info(f"Waiting for verification... ({wait_time} seconds elapsed)")
                sleep(check_interval)
                wait_time += check_interval
                continue
                
            # Check if we're on the feed page (successfully logged in)
            if "feed" in current_url or "linkedin.com/feed" in current_url:
                logger.info("\n✅ LOGIN SUCCESSFUL! You're on the LinkedIn feed.")
                is_logged_in = True
                
                # Save cookies for future use
                global cookies_jar
                cookies_jar = driver.get_cookies()
                logger.info(f"Saved {len(cookies_jar)} cookies for future use")
                
                # Now switch to headless mode since we're logged in
                logger.info("Login successful, now hiding browser window...")
                if switch_to_headless():
                    logger.info("Browser window hidden successfully")
                else:
                    logger.info("Failed to hide browser window, but login is successful")
                
                logger.info("="*80)
                logger.info("LOGIN PROCESS COMPLETED SUCCESSFULLY")
                logger.info("="*80 + "\n")
                return True
                    
            # Not on feed yet, but not on an obvious verification page either
            logger.info(f"Waiting for login to complete... ({wait_time} seconds elapsed)")
            sleep(check_interval)
            wait_time += check_interval
            
        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            sleep(check_interval)
            wait_time += check_interval
    
    # If we get here, check one more time if we're logged in
    try:
        if driver and ("feed" in driver.current_url or not driver.find_elements(By.ID, 'username')):
            logger.info("✅ Login successful!")
            is_logged_in = True
            
            # Save cookies for future use
            cookies_jar = driver.get_cookies()
            logger.info(f"Saved {len(cookies_jar)} cookies for future use")
            
            # Now switch to headless mode since we're logged in
            logger.info("Login successful, now hiding browser window...")
            if switch_to_headless():
                logger.info("Browser window hidden successfully")
            else:
                logger.info("Failed to hide browser window, but login is successful")
                
            return True
    except Exception as e:
        logger.error(f"Error in final login check: {e}")
    
    # If we get here, login timed out or failed
    logger.error("❌ Timed out or failed waiting for login")
    if driver:
        driver.quit()
        driver = None
    is_logged_in = False
    return False

def ensure_login():
    """Check if we're logged in, and if not, initiate login"""
    global driver, is_logged_in, cookies_jar
    
    # Always check driver validity even if logged in
    if is_logged_in and driver:
        try:
            # Test if driver is still responsive
            current_url = driver.current_url
            logger.info(f"Driver check: Current URL is {current_url}")
            # If we get here, driver is still valid
            return True
        except Exception as e:
            logger.error(f"Driver is no longer valid: {e}")
            is_logged_in = False
            driver = None
    
    # If we get here, either is_logged_in was False or driver was invalid
    try:
        # First try cookie login if we have cookies
        if cookies_jar:
            logger.info("Attempting login with saved cookies")
            if cookie_login():
                return True
            else:
                logger.warning("Cookie login failed, falling back to manual login")
                cookies_jar = None  # Clear invalid cookies
        
        # If cookie login failed or no cookies, fall back to manual login
        return manual_login()
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        return False

def scrape_company_about_page(driver, company_url):
    """Scrape the "About" page of a LinkedIn company"""
    about_url = f"{company_url}/about/"
    logger.info(f"Navigating to the about page: {about_url}")
    driver.get(about_url)
    sleep(3)
    
    if "login" in driver.current_url:
        logger.error("Session expired or not logged in. Cannot scrape about page.")
        return {}
    
    about_data = {
        'website': "",
        'phone': "",
        'associated_members': "",
        'founded': "",
        'specialties': "",
        'description': "",
        'headquarter': "",
        'industry': "",
        'company_size': ""
    }
    
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'lxml')
    
    try:
        description_p = soup.find('p', {'class': 'break-words white-space-pre-wrap t-black--light text-body-medium'})
        if description_p:
            about_data['description'] = description_p.get_text().strip()
            logger.info(f"Found company description: {about_data['description'][:50]}...")
    except Exception as e:
        logger.error(f"Error extracting company description: {e}")
    
    try:
        dt_elements = soup.find_all('dt')
        
        for dt in dt_elements:
            header_h3 = dt.find('h3', {'class': 'text-heading-medium'})
            if not header_h3:
                continue
                
            header_text = header_h3.get_text().strip()
            
            dd = dt.find_next('dd')
            if not dd:
                continue
                
            if "Website" in header_text:
                website_link = dd.find('a')
                if website_link:
                    about_data['website'] = website_link.get_text().strip()
                    logger.info(f"Found website: {about_data['website']}")
                    
            elif "Phone" in header_text:
                phone_link = dd.find('a')
                if phone_link:
                    phone_span = phone_link.find('span', {'class': 'link-without-visited-state'})
                    if phone_span:
                        about_data['phone'] = phone_span.get_text().strip()
                        logger.info(f"Found phone: {about_data['phone']}")
                        
            elif "Industry" in header_text:
                about_data['industry'] = dd.get_text().strip()
                logger.info(f"Found industry: {about_data['industry']}")
                
            elif "Company size" in header_text:
                size_text = dd.get_text().strip()
                about_data['company_size'] = size_text
                logger.info(f"Found company size: {about_data['company_size']}")
                
                associated_dd = dd.find_next('dd')
                if associated_dd:
                    associated_link = associated_dd.find('a')
                    if associated_link:
                        about_data['associated_members'] = associated_link.get_text().strip()
                        logger.info(f"Found associated members: {about_data['associated_members']}")
                        
            elif "Headquarters" in header_text:
                about_data['headquarter'] = dd.get_text().strip()
                logger.info(f"Found headquarters: {about_data['headquarter']}")
                
            elif "Founded" in header_text:
                about_data['founded'] = dd.get_text().strip()
                logger.info(f"Found founded year: {about_data['founded']}")
                
            elif "Specialties" in header_text:
                about_data['specialties'] = dd.get_text().strip()
                logger.info(f"Found specialties: {about_data['specialties'][:50]}...")
    
    except Exception as e:
        logger.error(f"Error processing about page structure: {e}")
    
    if not about_data['associated_members']:
        try:
            associated_link = soup.find('a', string=lambda t: t and 'associated members' in t.lower())
            if associated_link:
                about_data['associated_members'] = associated_link.get_text().strip()
                logger.info(f"Found associated members (direct approach): {about_data['associated_members']}")
        except Exception as e:
            logger.error(f"Error finding associated members: {e}")
    
    return about_data

def scrape_company_basics(driver, url):
    """Scrape basic information from a LinkedIn company page"""
    driver.get(url)
    logger.info(f"Scraping company page: {url}")
    sleep(2)
    
    if "login" in driver.current_url:
        logger.error("Session expired or not logged in. Cannot scrape.")
        return {"error": "Not logged in", "url": url}
    
    company_data = {
        'url': url,
        'name': "",
        'industry': "",
        'headquarter': "",
        'no of employees': "",
        'website': "",
        'phone': "",
        'associated_members': "",
        'founded': "",
        'specialties': "",
        'description': "",
        'key_personnel': {
            "founder & ceo": [],
            "vice president": [],
            "cto": [],
            "hr": []
        }
    }
    
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'lxml')
    
    try:
        name = soup.find('h1', {'class': 'org-top-card-summary__title'})
        if not name:
            name = soup.find('h1', {'class': 'top-card-layout__title'})
        
        if not name:
            name = soup.find('h1')
        
        if name:
            company_data['name'] = name.get_text().strip()
            logger.info(f"Found company name: {company_data['name']}")
    except Exception as e:
        logger.error(f"Error extracting company name: {e}")
    
    try:
        industry_dt = soup.find('dt', string=lambda t: t and 'Industry' in t)
        if industry_dt:
            industry_dd = industry_dt.find_next('dd')
            if industry_dd:
                company_data['industry'] = industry_dd.get_text().strip()
                logger.info(f"Found industry from page: {company_data['industry']}")
        
        if not company_data['industry']:
            for class_name in ['org-top-card-summary-info-list__info-item', 'top-card-layout__headline']:
                industry_elem = soup.find(['div', 'h2', 'span'], {'class': class_name})
                if industry_elem:
                    company_data['industry'] = industry_elem.get_text().strip()
                    logger.info(f"Found industry from top card: {company_data['industry']}")
                    break
    except Exception as e:
        logger.error(f"Error extracting company industry: {e}")
    
    try:
        hq_dt = soup.find('dt', string=lambda t: t and 'Headquarters' in t)
        if hq_dt:
            hq_dd = hq_dt.find_next('dd')
            if hq_dd:
                company_data['headquarter'] = hq_dd.get_text().strip()
                logger.info(f"Found headquarters from page: {company_data['headquarter']}")
        
        if not company_data['headquarter']:
            location_pattern = r'[\w\s-]+,\s+[\w\s-]+'
            location_elements = soup.find_all(['div', 'span'], string=lambda t: t and re.search(location_pattern, t) and not 'followers' in t.lower())
            
            for elem in location_elements:
                text = elem.get_text().strip()
                if re.search(location_pattern, text) and not text.endswith("followers") and not "industry" in text.lower():
                    company_data['headquarter'] = text
                    logger.info(f"Found headquarters from pattern match: {company_data['headquarter']}")
                    break
    except Exception as e:
        logger.error(f"Error extracting company headquarters: {e}")
    
    try:
        size_dt = soup.find('dt', string=lambda t: t and 'Company size' in t)
        if size_dt:
            size_dd = size_dt.find_next('dd')
            if size_dd:
                company_data['no of employees'] = size_dd.get_text().strip()
                logger.info(f"Found employee count from page: {company_data['no of employees']}")
        
        if not company_data['no of employees']:
            employee_count_span = soup.find('span', {'class': 't-normal t-black--light link-without-visited-state link-without-hover-state'})
            if employee_count_span and 'employee' in employee_count_span.get_text().lower():
                company_data['no of employees'] = employee_count_span.get_text().strip()
                logger.info(f"Found employee count from span: {company_data['no of employees']}")
    except Exception as e:
        logger.error(f"Error extracting employee count: {e}")
    
    about_data = scrape_company_about_page(driver, url)
    
    for key, value in about_data.items():
        if value:
            company_data[key] = value
    
    return company_data

def extract_profile_data(card):
    """Extract profile data from a LinkedIn profile card"""
    try:
        profile_data = {}
        
        name_element = card.find('a', {'class': 'app-aware-link'}) or card.find('a', {'class': 'link-without-visited-state'})
        if name_element:
            url = name_element.get('href', '')
            profile_data['url'] = url.split('?')[0] if '?' in url else url
            
            name_span = name_element.find('span', {'class': 'org-people-profile-card__profile-title'})
            if name_span:
                profile_data['name'] = name_span.get_text().strip()
            else:
                name_div = name_element.find('div')
                if name_div:
                    profile_data['name'] = name_div.get_text().strip()
                else:
                    link_text = name_element.get_text().strip()
                    if link_text and not link_text.startswith('http') and not link_text.startswith('www'):
                        profile_data['name'] = link_text
        
        title_div = card.find('div', {'class': 'lt-line-clamp--multi-line'}) or \
                   card.find('div', {'class': 'artdeco-entity-lockup__subtitle'}) or \
                   card.find('div', {'class': 'org-people-profile-card__subtitle'})
                   
        if title_div:
            profile_data['title'] = title_div.get_text().strip()
        
        if profile_data.get('name') or profile_data.get('url'):
            return profile_data
        return None
    except Exception as e:
        logger.error(f"Error in extract_profile_data: {e}")
        return None

def scroll_and_scrape_people(driver, all_employees):
    """Scroll through people page and scrape employee profiles"""
    scroll_count = 0
    consecutive_no_new_profiles = 0
    
    logger.info("Starting to scrape employee profiles...")
    
    while True:
        scroll_count += 1
        logger.info(f"Scroll attempt #{scroll_count}...")
        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'lxml')
        
        profile_cards = soup.find_all('li', {'class': 'grid'})
        
        if not profile_cards:
            profile_cards = soup.find_all('li', {'class': 'org-people-profiles-module__profile-item'})
            
        if not profile_cards:
            profile_cards = soup.find_all('li', {'class': 'org-people-profile-card'})
            
        if not profile_cards:
            # Try a more generic approach - find all list items with links
            all_li = soup.find_all('li')
            profile_cards = []
            for li in all_li:
                if li.find('a') and li.find('a').get('href') and '/in/' in li.find('a').get('href'):
                    profile_cards.append(li)
        
        if not profile_cards:
            logger.info("No profile cards found on this page.")
            break
        
        logger.info(f"Found {len(profile_cards)} profile cards on this scroll.")
        
        initial_length = len(all_employees)
        for card in profile_cards:
            try:
                profile_data = extract_profile_data(card)
                if profile_data and not any(p.get('url') == profile_data.get('url') for p in all_employees):
                    all_employees.append(profile_data)
                    if len(all_employees) % 10 == 0:
                        logger.info(f"Collected {len(all_employees)} profiles so far...")
            except Exception as e:
                logger.error(f"Error extracting profile: {e}")
        
        new_profiles_found = len(all_employees) - initial_length
        logger.info(f"Found {new_profiles_found} new profiles in this scroll.")
        
        if new_profiles_found == 0:
            consecutive_no_new_profiles += 1
            logger.info(f"No new profiles found for {consecutive_no_new_profiles} consecutive scrolls.")
        else:
            consecutive_no_new_profiles = 0
        
        if consecutive_no_new_profiles >= 3:
            logger.info("No new profiles for 3 consecutive scrolls. Ending search.")
            break
        
        try:
            show_more_button = driver.find_element(By.XPATH, "//button[contains(., 'Show more')]")
            if not show_more_button.is_displayed() or not show_more_button.is_enabled():
                logger.info("'Show more' button is not clickable. Ending search.")
                break
                
            logger.info("Clicking 'Show more' button...")
            driver.execute_script("arguments[0].click();", show_more_button)
            sleep(3)
        except Exception as e:
            logger.info(f"No 'Show more' button found ({str(e)}). Scrolling down instead.")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(3)
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
            sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(3)
    
    logger.info(f"Finished scraping people. Found a total of {len(all_employees)} employee profiles.")

def identify_key_personnel(all_employees, company_data):
    """Identify key personnel from employee profiles"""
    role_keywords = {
        "founder & ceo": ["founder", "ceo", "chief executive officer", "co-founder", "founder & ceo", "cofounder"],
        "vice president": ["vice president", "vp", "executive vice president", "senior vice president", "evp", "svp"],
        "cto": ["cto", "chief technology officer", "chief technical officer", "vp of technology", 
               "vp of engineering", "head of technology", "head of engineering", "tech lead"],
        "hr": ["hr", "human resources", "people and culture", "people operations", "talent", 
              "recruiting", "people officer", "chro", "chief human resources"]
    }
    
    role_counts = {role: 0 for role in role_keywords}
    
    logger.info("\nIdentifying key personnel by role...")
    for employee in all_employees:
        if "title" in employee and employee["title"]:
            title_lower = employee["title"].lower()
            
            for role, keywords in role_keywords.items():
                try:
                    if any(keyword in title_lower for keyword in keywords):
                        person_copy = {k: v for k, v in employee.items() if k != 'role'}
                        
                        if role not in company_data["key_personnel"]:
                            company_data["key_personnel"][role] = []
                        
                        if not any(p.get('url') == person_copy.get('url') for p in company_data["key_personnel"][role]):
                            company_data["key_personnel"][role].append(person_copy)
                            role_counts[role] += 1
                        break
                except Exception as e:
                    logger.error(f"ERROR: {e}")
    
    for role, count in role_counts.items():
        logger.info(f"Found {count} {role} personnel")
    
    return role_counts

def scrape_company_people(driver, company_url, company_data):
    """Scrape people data for a LinkedIn company"""
    # First try the /people/ page
    people_url = f"{company_url}/people/"
    driver.get(people_url)
    logger.info(f"Navigating to company's people page: {people_url}")
    sleep(3)
    
    if "login" in driver.current_url:
        logger.error("Session expired or not logged in. Cannot scrape people.")
        return company_data
    
    all_employees = []
    
    # Try to get employee names from the people page
    logger.info("Attempting to scrape from /people/ page...")
    scroll_and_scrape_people(driver, all_employees)
    
    # If we didn't find any employees, try the main company page as fallback
    if len(all_employees) == 0:
        logger.info("No employees found on /people/ page. Trying main company page...")
        driver.get(company_url)
        sleep(3)
        
        # Look for "See all employees" link and click it if found
        try:
            see_all_link = driver.find_element(By.XPATH, "//a[contains(text(), 'See all')]")
            if see_all_link:
                logger.info("Found 'See all' link. Clicking it...")
                driver.execute_script("arguments[0].click();", see_all_link)
                sleep(3)
                
                # Now try scraping again
                scroll_and_scrape_people(driver, all_employees)
        except Exception as e:
            logger.error(f"Couldn't find 'See all' link: {e}")
    
    # If we still didn't find any employees, try one more approach
    if len(all_employees) == 0:
        logger.info("Still no employees found. Trying direct search...")
        
        # Get company name
        company_name = company_data.get('name', '')
        if company_name:
            search_url = f"https://www.linkedin.com/search/results/people/?keywords={company_name.replace(' ', '%20')}"
            driver.get(search_url)
            logger.info(f"Searching for employees with company name: {company_name}")
            sleep(3)
            
            # Try scraping again
            scroll_and_scrape_people(driver, all_employees)
    
    role_counts = identify_key_personnel(all_employees, company_data)
    
    logger.info("\nPersonnel Summary:")
    logger.info(f"Total profiles found: {len(all_employees)}")
    for role, count in role_counts.items():
        if count > 0:
            logger.info(f"- {role}: {count} people")
    
    return company_data

def save_to_json(data, filename):
    """Save data to a JSON file"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    logger.info(f"Data saved to {filename}")

def scrape_company(company_url):
    """Scrape a LinkedIn company page and save the data"""
    global driver, is_logged_in, is_scraping, current_job
    
    is_scraping = True
    current_job = {"url": company_url, "start_time": int(time.time())}
    
    try:
        if not is_logged_in:
            logger.info("Not logged in. Attempting to log in...")
            if not ensure_login():
                is_scraping = False
                current_job = None
                return {"error": "Failed to log in", "status": "error"}
        
        logger.info("\n" + "="*80)
        logger.info(f"STARTING SCRAPE FOR: {company_url}")
        logger.info("="*80)
        
        company_data = scrape_company_basics(driver, company_url)
        
        if "error" in company_data:
            is_scraping = False
            current_job = None
            return {"error": company_data["error"], "status": "error", "url": company_url}
        
        company_data = scrape_company_people(driver, company_url, company_data)
        
        company_name = company_data.get('name')
        if not company_name or company_name.strip() == "":
            company_name = "company"
        company_name = company_name.replace(" ", "_").lower()
        filename = f"data/{company_name}_data.json"
        
        save_to_json(company_data, filename)
        
        # Count personnel
        total_personnel = 0
        for role, personnel in company_data["key_personnel"].items():
            total_personnel += len(personnel)
        
        result = {
            "status": "success",
            "company_name": company_data.get('name', 'Unknown'),
            "url": company_url,
            "file_path": filename,
            "personnel_count": total_personnel,
            "data": company_data
        }
        
        return result
    except Exception as e:
        logger.error(f"Error in scrape_company: {e}")
        return {
            "status": "error",
            "message": str(e),
            "url": company_url
        }
    finally:
        # Always clean up resources in finally block
        is_scraping = False
        current_job = None

# API Routes
@app.route('/status', methods=['GET'])
def status():
    """Check current scraping status"""
    try:
        global is_scraping, current_job, is_logged_in
        
        if current_job:
            current_job["duration"] = int(time.time()) - current_job["start_time"]
        
        return jsonify({
            "logged_in": is_logged_in,
            "is_scraping": is_scraping,
            "current_job": current_job
        })
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}")
        return jsonify({"error": str(e), "status": "error"})

@app.route('/login', methods=['GET'])
def login():
    """Manual login endpoint"""
    global is_logged_in, driver
    
    if is_logged_in:
        return jsonify({
            "status": "already_logged_in",
            "message": "Already logged in to LinkedIn"
        })
    
    try:
        if manual_login():
            return jsonify({
                "status": "success",
                "message": "Successfully logged in to LinkedIn"
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to log in to LinkedIn"
            }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error during login: {str(e)}"
        }), 500

# New Remote Login Endpoints
@app.route('/remote-login', methods=['GET'])
def remote_login():
    """Return login URL for frontend to handle login"""
    global is_logged_in
    
    if is_logged_in:
        return jsonify({
            "status": "already_logged_in",
            "message": "Already logged in to LinkedIn"
        })
    
    return jsonify({
        "status": "ready_for_login",
        "login_url": "https://www.linkedin.com/login",
        "message": "Please log in to LinkedIn in your browser, then submit your session cookies."
    })

@app.route('/submit-session', methods=['POST'])
def submit_session():
    """Receive and store LinkedIn cookies from frontend"""
    global cookies_jar, is_logged_in
    
    try:
        data = request.json
        if not data or 'cookies' not in data:
            return jsonify({
                "status": "error",
                "message": "No cookies data provided"
            }), 400
            
        cookies = data['cookies']
        if not cookies or not isinstance(cookies, list) or len(cookies) == 0:
            return jsonify({
                "status": "error",
                "message": "Invalid cookie format"
            }), 400
            
        logger.info(f"Received {len(cookies)} cookies from frontend")
        
        # Store the cookies
        cookies_jar = cookies
        
        # Validate the cookies immediately
        if cookie_login():
            return jsonify({
                "status": "success",
                "message": "Successfully logged in with provided cookies",
                "verified": True
            })
        else:
            cookies_jar = None
            return jsonify({
                "status": "error",
                "message": "Cookies were received but login failed. Please try again."
            }), 400
            
    except Exception as e:
        logger.error(f"Error processing submitted session: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error processing cookies: {str(e)}"
        }), 500

@app.route('/remote-login-check', methods=['GET'])
def remote_login_check():
    """Check if remote login was successful"""
    global is_logged_in
    
    return jsonify({
        "status": "success" if is_logged_in else "not_logged_in",
        "logged_in": is_logged_in
    })

@app.route('/company', methods=['GET'])
def company_endpoint():
    """Endpoint to start scraping a LinkedIn company"""
    global is_scraping, is_logged_in, driver, current_job, job_results
    
    company_url = request.args.get('url')
    force = request.args.get('force', 'false').lower() == 'true'
    
    if not company_url:
        return jsonify({
            "status": "error",
            "message": "Missing URL parameter. Use /company?url=https://www.linkedin.com/company/example"
        }), 400
        
    # Clean up the URL to ensure it's a LinkedIn company page
    if not company_url.startswith('https://www.linkedin.com/company/'):
        # Try to extract company name if full URL provided
        if 'linkedin.com/company/' in company_url:
            parts = company_url.split('linkedin.com/company/')
            if len(parts) > 1:
                company_name = parts[1].split('/')[0].split('?')[0]
                company_url = f"https://www.linkedin.com/company/{company_name}"
        else:
            return jsonify({
                "status": "error", 
                "message": "Invalid URL. Please provide a URL in the format https://www.linkedin.com/company/company-name"
            }), 400
    
    # Check if we're already scraping
    if is_scraping and not force:
        return jsonify({
            "status": "busy",
            "message": "Already scraping another company. Add ?force=true to override.",
            "current_job": current_job
        }), 409
    
    # Start the scraping process
    def run_scrape():
        global job_results, is_scraping, current_job, driver, is_logged_in
        
        # Reset state if force=true
        if force and is_scraping:
            logger.info("Forced scraping requested. Resetting previous scraping job.")
            try:
                if driver:
                    driver.quit()
                    driver = None
            except Exception as e:
                logger.error(f"Error closing driver during force reset: {e}")
            finally:
                is_scraping = False
                current_job = None
                is_logged_in = False
        
        try:
            # Make sure we're logged in first
            logger.info("\n" + "="*80)
            logger.info(f"STARTING LINKEDIN SCRAPE FOR: {company_url}")
            logger.info("="*80)
            
            if not is_logged_in or not driver:
                logger.info("LinkedIn login required before scraping")
                login_success = ensure_login()  # Use ensure_login which tries cookies first
                if not login_success:
                    error_msg = "Failed to log in to LinkedIn. Please try running the scraper again."
                    logger.error(f"ERROR: {error_msg}")
                    job_results[company_url] = {
                        "status": "error",
                        "message": error_msg,
                        "url": company_url
                    }
                    is_scraping = False
                    current_job = None
                    return
            else:
                logger.info("Already logged in, continuing with scraping")
            
            # Execute the actual scraping
            result = scrape_company(company_url)
            
            # Store the result
            job_results[company_url] = result
            
            # Print the final result in terminal to confirm completion
            logger.info("\n" + "="*80)
            if result["status"] == "success":
                logger.info(f"✅ SCRAPING COMPLETED SUCCESSFULLY FOR: {company_url}")
                
                # Print summary of results
                logger.info("\n📋 SUMMARY:")
                company_data = result["data"]
                logger.info(f"Company: {company_data.get('name', 'Unknown')}")
                logger.info(f"Industry: {company_data.get('industry', 'Not found')}")
                logger.info(f"Location: {company_data.get('headquarter', 'Not found')}")
                logger.info(f"Size: {company_data.get('company_size', 'Not found')}")
                logger.info("\nKey Personnel:")
                for role, personnel in company_data["key_personnel"].items():
                    if personnel:
                        logger.info(f"- {role.title()}: {len(personnel)} found")
            else:
                logger.info(f"❌ SCRAPING FAILED FOR: {company_url}")
                logger.info(f"Error: {result.get('message', 'Unknown error')}")
            
            logger.info("="*80)
            
        except Exception as e:
            logger.error("\n" + "="*80)
            logger.error(f"ERROR SCRAPING COMPANY: {company_url}")
            logger.error(f"Error details: {str(e)}")
            logger.error("="*80)
            
            # Create error result
            error_result = {
                "status": "error",
                "company_name": "Unknown",
                "url": company_url,
                "error": str(e),
                "message": "Scraping failed due to an error."
            }
            
            # Store the error result
            job_results[company_url] = error_result
        finally:
            # Update state flags
            is_scraping = False
            if current_job:
                current_job["end_time"] = int(time.time())
                if current_job.get("start_time"):
                    current_job["duration"] = current_job["end_time"] - current_job["start_time"]
            current_job = None
            
            logger.info("\n🏁 Scraping job complete.")
            logger.info("You can close the browser window if you're finished.")
    
    thread = Thread(target=run_scrape)
    thread.daemon = True
    thread.start()
    
    # Check if remote login is needed
    login_message = "A browser window will open for you to log in to LinkedIn manually. Please complete any verification steps LinkedIn requires."
    if not is_logged_in and cookies_jar is None:
        login_message = "Please log in using the /remote-login endpoint first, then retry this request."
    
    return jsonify({
        "status": "started",
        "message": f"Scraping job started for {company_url}. {login_message}",
        "url": company_url
    })

@app.route('/results', methods=['GET'])
def get_results():
    """Get results of completed scraping jobs"""
    url = request.args.get('url')
    
    if url:
        # Return results for a specific URL
        if url in job_results:
            return jsonify(job_results[url])
        else:
            return jsonify({
                "status": "error",
                "message": f"No results found for URL: {url}"
            }), 404
    else:
        # Return list of all URLs with results
        return jsonify({
            "status": "success",
            "urls": list(job_results.keys())
        })

@app.route('/company/company', methods=['GET'])
def get_company_data():
    """Get the latest company data from file"""
    try:
        # Get the most recent data file
        data_files = [f for f in os.listdir('data') if f.endswith('_data.json')]
        if not data_files:
            return jsonify({
                "status": "error",
                "message": "No company data files found"
            }), 404
            
        # Sort by modification time (newest first)
        latest_file = sorted(data_files, 
                            key=lambda f: os.path.getmtime(os.path.join('data', f)), 
                            reverse=True)[0]
        
        # Read the file
        with open(os.path.join('data', latest_file), 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify({
            "status": "success",
            "data": data
        })
    except Exception as e:
        logger.error(f"Error retrieving company data from file: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/logs', methods=['GET'])
def get_logs():
    """Return the contents of the log file"""
    try:
        with open('scraper.log', 'r') as f:
            log_lines = f.readlines()
            
        # Return the last 200 lines by default, or as specified
        num_lines = request.args.get('lines', 200, type=int)
        return jsonify({
            "status": "success", 
            "logs": log_lines[-num_lines:]
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error reading log file: {str(e)}"
        }), 500
        
@app.route('/reset', methods=['GET'])
def reset_scraper():
    """Reset the scraper's state completely"""
    global is_scraping, is_logged_in, driver, current_job, cookies_jar
    
    try:
        # Properly close the driver if it exists
        if driver:
            driver.quit()
    except Exception as e:
        logger.error(f"Error closing driver during reset: {e}")
    
    # Reset all global variables
    is_scraping = False
    is_logged_in = False
    driver = None
    current_job = None
    cookies_jar = None
    
    return jsonify({"status": "success", "message": "Scraper state completely reset"})

@app.route('/proxy/salesql', methods=['GET'])
def proxy_salesql():
    """
    Proxy requests to SalesQL API to avoid CORS issues
    
    Request:
    GET /proxy/salesql?linkedin_url=https://www.linkedin.com/in/abhishek-gupta-ag33
    
    Response:
    SalesQL API response
    """
    try:
        linkedin_url = request.args.get('linkedin_url')
        if not linkedin_url:
            return jsonify({
                "status": "error",
                "message": "Missing linkedin_url parameter"
            }), 400
            
        # SalesQL API key
        api_key = "JdKM5dJJfb7mZCjxQvhNhSBFbEjShRlA"
        
        # Clean up the LinkedIn URL to ensure it's valid
        linkedin_url = linkedin_url.strip()
        if not linkedin_url.startswith('http'):
            linkedin_url = 'https://' + linkedin_url
            
        # Remove any trailing slashes
        linkedin_url = linkedin_url.rstrip('/')
        
        logger.info(f"Making SalesQL API request for: {linkedin_url}")
        
        # Make request to SalesQL API with improved error handling
        import requests
        try:
            response = requests.get(
                "https://api-public.salesql.com/v1/persons/enrich",
                params={
                    "linkedin_url": linkedin_url,
                    "api_key": api_key
                },
                timeout=30
            )
            
            # Try to parse JSON response
            response_data = response.json()
            logger.info(f"SalesQL API response status code: {response.status_code}")
            
            # Return the response data
            return jsonify(response_data)
            
        except requests.exceptions.HTTPError as http_err:
            status_code = getattr(http_err.response, 'status_code', 500)
            error_message = f"HTTP error from SalesQL API: {http_err}"
            
            logger.error(f"SalesQL API HTTP error: {status_code} - {error_message}")
            
            return jsonify({
                "status": "error",
                "code": status_code,
                "message": "Person not found in SalesQL database" if status_code == 404 else error_message
            }), 200  # Return 200 so frontend can handle it gracefully
            
        except requests.exceptions.RequestException as req_err:
            error_type = type(req_err).__name__
            logger.error(f"SalesQL API request error ({error_type}): {req_err}")
            
            return jsonify({
                "status": "error",
                "message": f"SalesQL API request failed: {req_err}"
            }), 200
            
        except ValueError as json_err:
            logger.error(f"SalesQL API JSON parsing error: {json_err}")
            
            # If we reach this point, the request succeeded but returned invalid JSON
            # Try to get the raw response text
            raw_text = getattr(response, 'text', 'No response text available')
            
            return jsonify({
                "status": "error",
                "message": "Invalid JSON response from SalesQL API",
                "raw_response": raw_text[:500]  # Include part of raw response for debugging
            }), 200
            
    except Exception as e:
        logger.error(f"Error proxying SalesQL request: {e}")
        return jsonify({
            "status": "error",
            "message": f"Failed to proxy SalesQL request: {str(e)}"
        }), 200  # Return 200 so frontend can handle it gracefully
        
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path != "" and os.path.exists("static/" + path):
        return send_from_directory("static", path)
    else:
        return send_from_directory("static", "index.html")

# Start the Flask server when run directly
if __name__ == '__main__':
    try:
        # Create necessary directories
        os.makedirs("data", exist_ok=True)
        os.makedirs("static", exist_ok=True)  # Ensure static directory exists
        
        # Create a basic index.html if it doesn't exist
        if not os.path.exists("static/index.html"):
            with open("static/index.html", "w") as f:
                f.write("<html><body><h1>LinkedIn Company Scraper</h1><p>Use the API endpoints to interact with the scraper.</p></body></html>")
        
        # Start the Flask server
        logger.info("Starting LinkedIn Company Scraper...")
        logger.info("Access the web interface via API endpoints at http://localhost:5003")
        app.run(host='0.0.0.0', port=5003, debug=True)
    except KeyboardInterrupt:
        logger.info("\nShutting down the server...")
        if driver:
            driver.quit()

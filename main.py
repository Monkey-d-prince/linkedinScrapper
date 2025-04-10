import os
import json
import pickle
import re
import requests
from time import sleep
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def save_cookies(driver, path):
    with open(path, 'wb') as file:
        pickle.dump(driver.get_cookies(), file)
    print(f"Cookies saved to {path}")

def load_cookies(driver, path):
    try:
        with open(path, 'rb') as file:
            cookies = pickle.load(file)
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    print(f"Warning: Could not load cookie: {e}")
        print("Cookies loaded")
        return True
    except Exception as e:
        print(f"Error loading cookies: {e}")
        return False

def initial_login_with_verification(driver, email, password):
    driver.get('https://www.linkedin.com/login')
    print(f"Current page title: {driver.title}")
    
    email_field = driver.find_element(By.ID, 'username')
    email_field.send_keys(email)
    
    password_field = driver.find_element(By.ID, 'password')
    password_field.send_keys(password)
    
    password_field.submit()
    
    print("\n⚠️ ATTENTION ⚠️")
    print("You may need to complete the verification process in your LinkedIn app.")
    input("Press Enter after you have completed the verification and are logged in...")
    
    sleep(3)
    
    if "feed" in driver.current_url:
        print("Login successful!")
        save_cookies(driver, "linkedin_cookies.pkl")
        return True
    else:
        print("Login may have failed. Please check if you're properly logged in.")
        return False

def login_with_cookies(driver):
    driver.get('https://www.linkedin.com')
    sleep(1)
    
    if not load_cookies(driver, "linkedin_cookies.pkl"):
        return False
    
    driver.refresh()
    sleep(3)
    
    if "feed" in driver.current_url or not driver.find_elements(By.ID, 'username'):
        print("Login with cookies successful")
        return True
    else:
        print("Login with cookies failed. You may need to obtain new cookies.")
        return False

def scrape_company_about_page(driver, company_url):
    about_url = f"{company_url}/about/"
    print(f"Navigating to the about page: {about_url}")
    driver.get(about_url)
    sleep(3)
    
    if "login" in driver.current_url:
        print("Session expired or not logged in. Cannot scrape about page.")
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
            print(f"Found company description: {about_data['description'][:50]}...")
    except Exception as e:
        print(f"Error extracting company description: {e}")
    
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
                    print(f"Found website: {about_data['website']}")
                    
            elif "Phone" in header_text:
                phone_link = dd.find('a')
                if phone_link:
                    phone_span = phone_link.find('span', {'class': 'link-without-visited-state'})
                    if phone_span:
                        about_data['phone'] = phone_span.get_text().strip()
                        print(f"Found phone: {about_data['phone']}")
                        
            elif "Industry" in header_text:
                about_data['industry'] = dd.get_text().strip()
                print(f"Found industry: {about_data['industry']}")
                
            elif "Company size" in header_text:
                size_text = dd.get_text().strip()
                about_data['company_size'] = size_text
                print(f"Found company size: {about_data['company_size']}")
                
                associated_dd = dd.find_next('dd')
                if associated_dd:
                    associated_link = associated_dd.find('a')
                    if associated_link:
                        about_data['associated_members'] = associated_link.get_text().strip()
                        print(f"Found associated members: {about_data['associated_members']}")
                        
            elif "Headquarters" in header_text:
                about_data['headquarter'] = dd.get_text().strip()
                print(f"Found headquarters: {about_data['headquarter']}")
                
            elif "Founded" in header_text:
                about_data['founded'] = dd.get_text().strip()
                print(f"Found founded year: {about_data['founded']}")
                
            elif "Specialties" in header_text:
                about_data['specialties'] = dd.get_text().strip()
                print(f"Found specialties: {about_data['specialties'][:50]}...")
    
    except Exception as e:
        print(f"Error processing about page structure: {e}")
    
    if not about_data['associated_members']:
        try:
            associated_link = soup.find('a', string=lambda t: t and 'associated members' in t.lower())
            if associated_link:
                about_data['associated_members'] = associated_link.get_text().strip()
                print(f"Found associated members (direct approach): {about_data['associated_members']}")
        except Exception as e:
            print(f"Error finding associated members: {e}")
    
    return about_data

def scrape_company_basics(driver, url):
    driver.get(url)
    print(f"Scraping company page: {url}")
    sleep(2)
    
    if "login" in driver.current_url:
        print("Session expired or not logged in. Cannot scrape.")
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
            print(f"Found company name: {company_data['name']}")
    except Exception as e:
        print(f"Error extracting company name: {e}")
    
    try:
        industry_dt = soup.find('dt', string=lambda t: t and 'Industry' in t)
        if industry_dt:
            industry_dd = industry_dt.find_next('dd')
            if industry_dd:
                company_data['industry'] = industry_dd.get_text().strip()
                print(f"Found industry from page: {company_data['industry']}")
        
        if not company_data['industry']:
            for class_name in ['org-top-card-summary-info-list__info-item', 'top-card-layout__headline']:
                industry_elem = soup.find(['div', 'h2', 'span'], {'class': class_name})
                if industry_elem:
                    company_data['industry'] = industry_elem.get_text().strip()
                    print(f"Found industry from top card: {company_data['industry']}")
                    break
    except Exception as e:
        print(f"Error extracting company industry: {e}")
    
    try:
        hq_dt = soup.find('dt', string=lambda t: t and 'Headquarters' in t)
        if hq_dt:
            hq_dd = hq_dt.find_next('dd')
            if hq_dd:
                company_data['headquarter'] = hq_dd.get_text().strip()
                print(f"Found headquarters from page: {company_data['headquarter']}")
        
        if not company_data['headquarter']:
            location_pattern = r'[\w\s-]+,\s+[\w\s-]+'
            location_elements = soup.find_all(['div', 'span'], string=lambda t: t and re.search(location_pattern, t) and not 'followers' in t.lower())
            
            for elem in location_elements:
                text = elem.get_text().strip()
                if re.search(location_pattern, text) and not text.endswith("followers") and not "industry" in text.lower():
                    company_data['headquarter'] = text
                    print(f"Found headquarters from pattern match: {company_data['headquarter']}")
                    break
    except Exception as e:
        print(f"Error extracting company headquarters: {e}")
    
    try:
        size_dt = soup.find('dt', string=lambda t: t and 'Company size' in t)
        if size_dt:
            size_dd = size_dt.find_next('dd')
            if size_dd:
                company_data['no of employees'] = size_dd.get_text().strip()
                print(f"Found employee count from page: {company_data['no of employees']}")
        
        if not company_data['no of employees']:
            employee_count_span = soup.find('span', {'class': 't-normal t-black--light link-without-visited-state link-without-hover-state'})
            if employee_count_span and 'employee' in employee_count_span.get_text().lower():
                company_data['no of employees'] = employee_count_span.get_text().strip()
                print(f"Found employee count from span: {company_data['no of employees']}")
    except Exception as e:
        print(f"Error extracting employee count: {e}")
    
    about_data = scrape_company_about_page(driver, url)
    
    for key, value in about_data.items():
        if value:
            company_data[key] = value
    
    return company_data

def extract_profile_data(card):
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
        print(f"Error in extract_profile_data: {e}")
        return None

def scroll_and_scrape_people(driver, all_employees):
    scroll_count = 0
    consecutive_no_new_profiles = 0
    
    print("Starting to scrape employee profiles...")
    
    while True:
        scroll_count += 1
        print(f"Scroll attempt #{scroll_count}...")
        
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
            print("No profile cards found on this page.")
            break
        
        print(f"Found {len(profile_cards)} profile cards on this scroll.")
        
        initial_length = len(all_employees)
        for card in profile_cards:
            try:
                profile_data = extract_profile_data(card)
                if profile_data and not any(p.get('url') == profile_data.get('url') for p in all_employees):
                    all_employees.append(profile_data)
                    if len(all_employees) % 10 == 0:
                        print(f"Collected {len(all_employees)} profiles so far...")
            except Exception as e:
                print(f"Error extracting profile: {e}")
        
        new_profiles_found = len(all_employees) - initial_length
        print(f"Found {new_profiles_found} new profiles in this scroll.")
        
        if new_profiles_found == 0:
            consecutive_no_new_profiles += 1
            print(f"No new profiles found for {consecutive_no_new_profiles} consecutive scrolls.")
        else:
            consecutive_no_new_profiles = 0
        
        if consecutive_no_new_profiles >= 3:
            print("No new profiles for 3 consecutive scrolls. Ending search.")
            break
        
        try:
            show_more_button = driver.find_element(By.XPATH, "//button[contains(., 'Show more')]")
            if not show_more_button.is_displayed() or not show_more_button.is_enabled():
                print("'Show more' button is not clickable. Ending search.")
                break
                
            print("Clicking 'Show more' button...")
            driver.execute_script("arguments[0].click();", show_more_button)
            sleep(3)
        except Exception as e:
            print(f"No 'Show more' button found ({str(e)}). Scrolling down instead.")
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(3)
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
            sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            sleep(3)
    
    print(f"Finished scraping people. Found a total of {len(all_employees)} employee profiles.")

def enrich_profile_with_salesql(linkedin_url, api_key):
    """
    Enrich a LinkedIn profile with email and phone information from SalesQL API.
    Returns a dictionary with enriched data or None if enrichment fails.
    Handles the nested email and phone structure from SalesQL including types.
    """
    try:
        # Remove any tracking parameters
        cleaned_url = linkedin_url.split('?')[0] if '?' in linkedin_url else linkedin_url
        
        base_url = "https://api-public.salesql.com/v1/persons/enrich"
        params = {
            "linkedin_url": cleaned_url,
            "api_key": api_key
        }
        
        print(f"Enriching profile: {cleaned_url}")
        response = requests.get(base_url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            enriched_data = {}
            
            # Handle the emails array in SalesQL's response with types
            if "emails" in data and isinstance(data["emails"], list):
                email_details = []
                for email_obj in data["emails"]:
                    if "email" in email_obj and email_obj["email"]:
                        email_info = {
                            "email": email_obj["email"],
                            "type": email_obj.get("type", "Unknown"),
                            "status": email_obj.get("status", "Unknown")
                        }
                        email_details.append(email_info)
                
                if email_details:
                    enriched_data["email_details"] = email_details
                    # Also keep the simple email list for backward compatibility
                    enriched_data["emails"] = [e["email"] for e in email_details]
                    print(f"Found emails: {email_details}")
            
            # Handle the phones array in SalesQL's response with types
            if "phones" in data and isinstance(data["phones"], list):
                phone_details = []
                for phone_obj in data["phones"]:
                    if "phone" in phone_obj and phone_obj["phone"]:
                        phone_info = {
                            "phone": phone_obj["phone"],
                            "type": phone_obj.get("type", "Unknown"),
                            "country_code": phone_obj.get("country_code", "Unknown"),
                            "is_valid": phone_obj.get("is_valid", False)
                        }
                        phone_details.append(phone_info)
                
                if phone_details:
                    enriched_data["phone_details"] = phone_details
                    # Also keep the simple phone list for backward compatibility
                    enriched_data["phones"] = [p["phone"] for p in phone_details]
                    print(f"Found phones: {phone_details}")
            
            # If we found either emails or phones, return the enriched data
            if enriched_data:
                print(f"Successfully enriched profile with: {enriched_data}")
                return enriched_data
            else:
                print("SalesQL API returned no useful contact data for this profile")
                return None
        elif response.status_code == 404:
            print(f"SalesQL API error: 404 - Profile not found")
            return None
        else:
            print(f"SalesQL API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error enriching profile with SalesQL: {e}")
        return None
def identify_key_personnel(all_employees, company_data, salesql_api_key=None):
    role_keywords = {
        "founder & ceo": ["founder", "ceo", "chief executive officer", "co-founder", "founder & ceo", "cofounder"],
        "vice president": ["vice president", "vp", "executive vice president", "senior vice president", "evp", "svp"],
        "cto": ["cto", "chief technology officer", "chief technical officer", "vp of technology", 
               "vp of engineering", "head of technology", "head of engineering", "tech lead"],
        "hr": ["hr", "human resources", "people and culture", "people operations", "talent", 
              "recruiting", "people officer", "chro", "chief human resources"]
    }
    
    role_counts = {role: 0 for role in role_keywords}
    
    print("\nIdentifying key personnel by role...")
    for employee in all_employees:
        if "title" in employee and employee["title"]:
            title_lower = employee["title"].lower()
            
            for role, keywords in role_keywords.items():
                try:
                    if any(keyword in title_lower for keyword in keywords):
                        person_copy = {k: v for k, v in employee.items() if k != 'role'}
                        
                        # Enrich profile with SalesQL data if URL exists and API key is provided
                        if salesql_api_key and person_copy.get('url'):
                            print(f"Enriching profile for {person_copy.get('name')} ({role})")
                            enriched_data = enrich_profile_with_salesql(person_copy['url'], salesql_api_key)
                            
                            if enriched_data:
                                # Update person data with enriched information
                                person_copy.update(enriched_data)
                            
                            # Add delay to avoid API rate limits
                            sleep(1)
                        
                        if role not in company_data["key_personnel"]:
                            company_data["key_personnel"][role] = []
                        
                        if not any(p.get('url') == person_copy.get('url') for p in company_data["key_personnel"][role]):
                            company_data["key_personnel"][role].append(person_copy)
                            role_counts[role] += 1
                        break
                except Exception as e:
                    print(f"ERROR: {e}")
    
    for role, count in role_counts.items():
        print(f"Found {count} {role} personnel")
    
    return role_counts

def scrape_company_people(driver, company_url, company_data, salesql_api_key=None):
    # First try the /people/ page
    people_url = f"{company_url}/people/"
    driver.get(people_url)
    print(f"Navigating to company's people page: {people_url}")
    sleep(3)
    
    if "login" in driver.current_url:
        print("Session expired or not logged in. Cannot scrape people.")
        return company_data
    
    all_employees = []
    
    # Try to get employee names from the people page
    print("Attempting to scrape from /people/ page...")
    scroll_and_scrape_people(driver, all_employees)
    
    # If we didn't find any employees, try the main company page as fallback
    if len(all_employees) == 0:
        print("No employees found on /people/ page. Trying main company page...")
        driver.get(company_url)
        sleep(3)
        
        # Look for "See all employees" link and click it if found
        try:
            see_all_link = driver.find_element(By.XPATH, "//a[contains(text(), 'See all')]")
            if see_all_link:
                print("Found 'See all' link. Clicking it...")
                driver.execute_script("arguments[0].click();", see_all_link)
                sleep(3)
                
                # Now try scraping again
                scroll_and_scrape_people(driver, all_employees)
        except Exception as e:
            print(f"Couldn't find 'See all' link: {e}")
    
    # If we still didn't find any employees, try one more approach
    if len(all_employees) == 0:
        print("Still no employees found. Trying direct search...")
        
        # Get company name
        company_name = company_data.get('name', '')
        if company_name:
            search_url = f"https://www.linkedin.com/search/results/people/?keywords={company_name.replace(' ', '%20')}"
            driver.get(search_url)
            print(f"Searching for employees with company name: {company_name}")
            sleep(3)
            
            # Try scraping again
            scroll_and_scrape_people(driver, all_employees)
    
    role_counts = identify_key_personnel(all_employees, company_data, salesql_api_key)
    
    print("\nPersonnel Summary:")
    print(f"Total profiles found: {len(all_employees)}")
    for role, count in role_counts.items():
        if count > 0:
            print(f"- {role}: {count} people")
    
    return company_data

def save_to_json(data, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Data saved to {filename}")

def extract_description_from_html(html_content):
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        
        p_tag = soup.find('p', {'class': 'break-words white-space-pre-wrap t-black--light text-body-medium'})
        
        if p_tag:
            description = p_tag.get_text().strip()
            print(f"Successfully extracted description from provided HTML")
            return description
        else:
            print("Could not find description in the provided HTML")
            return ""
    except Exception as e:
        print(f"Error extracting description from HTML: {e}")
        return ""

def enrich_existing_key_personnel(company_data, salesql_api_key):
    """
    Enrich existing key personnel data in JSON with SalesQL API
    """
    print("\nEnriching existing key personnel with SalesQL data...")
    
    enriched_count = 0
    for role, personnel_list in company_data["key_personnel"].items():
        role_enriched_count = 0
        
        for i, person in enumerate(personnel_list):
            if person.get('url') and not (person.get('emails') or person.get('phones')):
                print(f"Enriching {person.get('name', 'Unknown')} ({role})...")
                enriched_data = enrich_profile_with_salesql(person['url'], salesql_api_key)
                
                if enriched_data:
                    # Update person data with enriched information
                    company_data["key_personnel"][role][i].update(enriched_data)
                    role_enriched_count += 1
                    enriched_count += 1
                
                # Add delay to avoid API rate limits
                sleep(1)
        
        if role_enriched_count > 0:
            print(f"Enriched {role_enriched_count} {role} personnel records")
    
    print(f"Total enriched personnel: {enriched_count}")
    return company_data

def main():
    email = "prince0862gupta@gmail.com"
    password = "Prince297#"
    salesql_api_key = "JdKM5dJJfb7mZCjxQvhNhSBFbEjShRlA"  # Your SalesQL API key
    
    # Test a well-known LinkedIn profile to verify SalesQL API is working
    print("Testing SalesQL API with a well-known profile...")
    test_result = enrich_profile_with_salesql("https://www.linkedin.com/in/williamhgates/", salesql_api_key)
    if test_result:
        print("✅ SalesQL API test successful! API is working.")
    else:
        print("⚠️ SalesQL API test failed. API key may be invalid or rate limit reached.")
    
    driver = setup_driver()
    
    try:
        if os.path.exists("linkedin_cookies.pkl"):
            print("Found saved cookies. Attempting to log in with cookies...")
            if not login_with_cookies(driver):
                print("Cookie login failed. Trying manual login...")
                initial_login_with_verification(driver, email, password)
        else:
            print("No saved cookies found. Please complete the verification process...")
            initial_login_with_verification(driver, email, password)
        
        description_html = """<p class="break-words white-space-pre-wrap t-black--light text-body-medium"></p>"""
        
        description = extract_description_from_html(description_html)
        
        company_urls = [
            "https://www.linkedin.com/company/we360-ai",
        ]
        
        for url in company_urls:
            print("\n" + "="*80)
            print(f"STARTING SCRAPE FOR: {url}")
            print("="*80)
            
            company_data = scrape_company_basics(driver, url)
            
            if description and not company_data.get('description'):
                company_data['description'] = description
                print(f"Added description from provided HTML")
            
            company_data = scrape_company_people(driver, url, company_data, salesql_api_key)
            
            company_name = company_data.get('name')
            if not company_name or company_name.strip() == "":
                company_name = "company"
            company_name = company_name.replace(" ", "_").lower()
            filename = f"data/{company_name}_data.json"
            
            # Check if there's an existing file we need to enrich
            if os.path.exists(filename):
                print(f"Found existing data file for {company_name}. Loading for enrichment...")
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    
                    # Check if the existing data has key personnel that need enrichment
                    if existing_data.get("key_personnel"):
                        for role, personnel in existing_data["key_personnel"].items():
                            # Add personnel to current company_data if they don't already exist
                            if role not in company_data["key_personnel"]:
                                company_data["key_personnel"][role] = []
                            
                            for person in personnel:
                                if not any(p.get('url') == person.get('url') for p in company_data["key_personnel"][role]):
                                    company_data["key_personnel"][role].append(person)
                        
                        # Now enrich all personnel
                        company_data = enrich_existing_key_personnel(company_data, salesql_api_key)
                except Exception as e:
                    print(f"Error processing existing file: {e}")
            
            save_to_json(company_data, filename)
            
            print("\nFINAL DATA SUMMARY:")
            print(f"Company: {company_data.get('name', 'Unknown')}")
            print(f"Headquarters: {company_data.get('headquarter', 'Not found')}")
            print(f"Industry: {company_data.get('industry', 'Not found')}")
            print(f"Employees: {company_data.get('no of employees', 'Not found')}")
            print(f"Website: {company_data.get('website', 'Not found')}")
            print(f"Phone: {company_data.get('phone', 'Not found')}")
            print(f"Founded: {company_data.get('founded', 'Not found')}")
            print(f"Associated Members: {company_data.get('associated_members', 'Not found')}")
            print(f"Description: {company_data.get('description', 'Not found')[:50]}...")
            
            # Count enriched personnel
            enriched_count = 0
            total_personnel = 0
            for role, personnel in company_data["key_personnel"].items():
                total_personnel += len(personnel)
                for person in personnel:
                    if person.get('emails') or person.get('phones'):
                        enriched_count += 1
            
            personnel_counts = {role: len(people) for role, people in company_data["key_personnel"].items()}
            print("Key Personnel Count by Role:", personnel_counts)
            print(f"Successfully enriched {enriched_count}/{total_personnel} personnel records with contact information")
            print(f"Data saved to: {filename}")
            print("="*80)
            
            if company_urls.index(url) < len(company_urls) - 1:
                print("Pausing before next company...")
                sleep(2)
    
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}")
    
    finally:
        driver.quit()
        print("Scraping completed")

if __name__ == "__main__":
    main()
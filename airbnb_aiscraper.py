import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import openai
import html2text
import tiktoken
import time
import os
import pandas as pd
import json
# from dotenv import load_dotenv, find_dotenv
from selenium.webdriver.chrome.service import Service

openai.api_key = st.secrets["OPENAI_API_KEY"]

# Configure Chrome options
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import streamlit as st
import os

def get_driver():
    """Create and return a configured WebDriver instance."""
    chrome_options = Options()

    # Required options for headless operation
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Recommended options for Streamlit Cloud and other cloud environments
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-extensions")  # Remove if you’re adding an extension
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")

    # Add Chrome extension (optional)
    extension_path = "path/to/extension.crx"  # Replace with the actual path to your extension
    if os.path.exists(extension_path):
        chrome_options.add_extension(extension_path)
    else:
        st.warning("Extension file not found. Running without extension.")

    try:
        # Use webdriver-manager to automatically handle ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"Error initializing WebDriver: {str(e)}")
        raise


def get_html_content(driver, max_retries=3):
    """Fetch HTML content from the current page with retries."""
    for attempt in range(max_retries):
        try:
            WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            
            # Scroll gradually to trigger lazy-loading
            total_height = driver.execute_script("return document.body.scrollHeight")
            for i in range(3):
                driver.execute_script(f"window.scrollTo(0, {total_height * (i+1) / 3});")
                time.sleep(2)
            
            return driver.page_source
        except TimeoutException:
            if attempt == max_retries - 1:
                st.error(f"Timeout while loading the page after {max_retries} attempts")
                return None
            time.sleep(5)  # Wait before retrying
    return None

def parse_html(html_content):
    """Parse and clean HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup(['script', 'style', 'footer']):
        element.decompose()
    return str(soup)

def clean_content(parsed_html):
    """Convert HTML to clean text."""
    h = html2text.HTML2Text()
    h.ignore_links = h.ignore_images = True
    h.body_width = 0
    return h.handle(parsed_html)

def split_text(text, max_tokens=2000):
    """Split text into chunks."""
    encoding = tiktoken.get_encoding("cl100k_base")## encoding to represents the token model can understand and process
    tokens = encoding.encode(text)
    return [encoding.decode(tokens[i:i + max_tokens]) for i in range(0, len(tokens), max_tokens)]

def extract_content_with_openai(cleaned_content, user_query):
    """Extract relevant information using OpenAI API."""
    try:
        response = openai.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[
                {"role": "system", "content": "You are a precise data extractor for Airbnb listings. Focus only on the current listing and extract exactly what is asked. Format the output clearly with labels."},
                {"role": "user", "content": f"From this single Airbnb listing, extract only: {user_query}\n\nListing Content:\n{cleaned_content}"}
            ],
            max_tokens=500,
            temperature=0.3,  # Lower temperature for more consistent output
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"OpenAI API error: {e}")
        return f"Error in content extraction: {str(e)}"



def get_listing_links(driver):
    """Get links to individual listings and their prices from the search results page."""
    try:
        wait = WebDriverWait(driver, 30)
        time.sleep(5)  # Wait for initial load
        
        # Scroll to load all content
        last_height = driver.execute_script("return document.body.scrollHeight")
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # Parse listings and prices
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        unique_links = set()
        listings_info = []

        listing_elements = soup.find_all('div', {'itemprop': 'itemListElement'})

        for element in listing_elements:
            url_meta = element.find('meta', {'itemprop': 'url'})
            price_span = element.find('span', class_="_11jcbg2")
            if url_meta and url_meta.get('content') and price_span:
                url = url_meta['content'].split('?')[0]  # Clean the URL
                price = price_span.text.strip() if price_span else "No price available"
                listings_info.append({'url': url, 'price': price})
                unique_links.add(url)
                st.write(f"Found listing: {url} with price: {price}")
        
        st.write(f"Total unique listings found: {len(listings_info)}")
        return listings_info
        
    except TimeoutException:
        st.error("Timeout while loading listing cards.")
        return []
    except Exception as e:
        st.error(f"Error in get_listing_links: {e}")
        return []
def process_listing(driver, link, user_query):
    """Process an individual listing and extract relevant information."""
    original_window = driver.current_window_handle  # Store the original window handle
    if not link.startswith('http'):
        link = f"https://{link if link.startswith('/') else '/' + link}"
    
    try:
        # Create new window with proper JavaScript execution
        driver.execute_script("window.open('about:blank', '_blank');")
        
        # Wait for the new window and switch to it
        WebDriverWait(driver, 10).until(EC.number_of_windows_to_be(2))
        
        # Switch to the new window
        new_window = [window for window in driver.window_handles if window != original_window][0]
        driver.switch_to.window(new_window)
        
        # Load the listing page with wait
        driver.get(link)
        time.sleep(3)  # Wait for initial load
        
        # Get HTML content
        html_content = get_html_content(driver)
        if not html_content:
            return f"Error: Unable to load content for {link}"
        
        # Process the content
        parsed_html = parse_html(html_content)
        clean_content_data = clean_content(parsed_html)
        
        # Only split if content is too long
        if len(clean_content_data) > 4000:  # Approximate token limit
            text_chunks = split_text(clean_content_data)
            extracted_info = []
            for chunk in text_chunks:
                info = extract_content_with_openai(chunk, user_query)
                extracted_info.append(info)
            result = " ".join(extracted_info)
        else:
            # Single extraction for shorter content
            result = extract_content_with_openai(clean_content_data, user_query)
            
    except Exception as e:
        st.error(f"Error processing listing: {str(e)}")
        return f"Error processing listing: {str(e)}"
        
    finally:
        try:
            # Properly close the new window and switch back
            if len(driver.window_handles) > 1:
                driver.close()  # Close current window
                driver.switch_to.window(original_window)  # Switch back to original
            elif driver.current_window_handle != original_window:
                driver.switch_to.window(original_window)
        except Exception as e:
            st.error(f"Error handling browser tabs: {str(e)}")
    
    return result
def main():
    st.title("Sequential Tab-based Airbnb Scraper")
    # Add session state
    if 'scraping_in_progress' not in st.session_state:
        st.session_state.scraping_in_progress = False
    
    url = st.text_input("Enter the Airbnb search URL:")
    user_query = st.text_input("What information do you want to extract? (e.g., 'property name, price, rating, amenities, and reviews')")
    
    if st.button("Start Scraping", disabled=st.session_state.scraping_in_progress):
        if url and user_query:
            st.session_state.scraping_in_progress = True
            
            with st.spinner("Initializing scraper..."):
                driver = get_driver()
                try:
                    # Load the base URL and get listings with prices
                    driver.get(url)
                    status_container = st.empty()
                    status_container.info("Loading search page...")
                    
                    listings_info = get_listing_links(driver)
                    if not listings_info:
                        st.error("No listings found. Please check the URL and try again.")
                        return
                        
                    status_container.info(f"Found {len(listings_info)} listings with prices.")
                    
                    results = []
                    progress_bar = st.progress(0)
                    
                    for idx, listing in enumerate(listings_info):
                        status_container.write(f"Processing listing {idx + 1}/{len(listings_info)}")
                        result = process_listing(driver, listing['url'], user_query)
                        results.append({'link': listing['url'], 'price':listing['price'],'data': result})
                        progress_bar.progress((idx + 1) / len(listings_info))
                        
                        # Display results in real-time
                        st.subheader(f"Listing {idx + 1}: {listing['url']}")
                        st.write(f"Price: {listing['price']}")
                        st.write(result)
                        st.markdown("---")
                        
                        time.sleep(3)  # Rate limiting between listings
                    
                    status_container.success("Scraping completed!")

                    if results:
                        processed_data =[]
                        for items in results:
                            link = items.get('link')
                            price= items.get('price')
                            data = items.get("data")

                            if isinstance(data,str):
                                try:
                                    data = json.loads(data)
                                except json.JSONDecodeError:
                                    print(f"failed to parse data for link:{link}")
                                    data={"extracted_info":data}
                            elif isinstance(data,list):
                                merged_data={}
                                for entry in data:
                                    if isinstance(entry,dict):
                                        merged_data.update(entry)
                                    else:
                                        merged_data['additional_info']=entry
                                data = merged_data
                            elif not isinstance(data,dict):
                                data={'extracted_info':str(data)}
                            combined_data = {"link":link,'price':price}
                            combined_data.update(data)
                            processed_data.append(combined_data)
                        df = pd.DataFrame(processed_data)
                        st.subheader("Aggregated Data")
                        st.dataframe(df)
                        df.to_csv('airbnb_listings.csv', index=False)

                    else:
                        st.write("No data was collected")
                    
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                finally:
                    driver.quit()
                    st.session_state.scraping_in_progress = False

        
        else:
            st.warning("Please provide both a URL and a query.")
if __name__ == "__main__":
    main()
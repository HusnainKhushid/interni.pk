import requests
from bs4 import BeautifulSoup
import re
import json
import time
from datetime import datetime

# --- Configuration ---
# Hardcoded parameters for the demonstration
SEARCH_QUERY = "Internship" # The job title or keyword to search for
MAX_PAGES_TO_SCRAPE = 2      # Limit the number of search result pages to fetch
MAX_JOBS_TO_PROCESS = 10     # Limit the total number of job details to fetch and display
REQUEST_TIMEOUT = 15         # Seconds before timing out a request
DELAY_BETWEEN_PAGES = 2      # Seconds to wait between fetching search result pages
DELAY_BETWEEN_DETAILS = 1    # Seconds to wait between fetching individual job details

# --- Helper Function ---

def fetch_page(url, max_attempts=3, timeout=REQUEST_TIMEOUT):
    """
    Fetches content from a URL with retries and a user-agent header.

    Args:
        url (str): The URL to fetch.
        max_attempts (int): Maximum number of retry attempts.
        timeout (int): Request timeout in seconds.

    Returns:
        requests.Response or None: The response object if successful, None otherwise.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status() # Check for HTTP errors (4xx or 5xx)
            print(f"Successfully fetched: {url} (Status: {response.status_code})")
            return response
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed for url: {url} with error: {e}")
            if attempt < max_attempts - 1:
                # Exponential backoff for retries
                wait_time = 2 ** attempt
                print(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Skipping {url} after {max_attempts} failed attempts.")
    return None

# --- Core Scraping Function ---

def scrape_and_display_rozee(query, max_pages, max_jobs):
    """
    Scrapes job listings from Rozee.pk based on the query and displays them.

    Args:
        query (str): The search term (e.g., "Internship", "Software Engineer").
        max_pages (int): The maximum number of search result pages to scrape.
        max_jobs (int): The maximum total number of job details to fetch and display.
    """
    base_search_url = f"https://www.rozee.pk/job/jsearch/q/{query.replace(' ', '%20')}"
    scraped_jobs_data = []
    jobs_processed_count = 0

    print(f"--- Starting Rozee.pk Scraper ---")
    print(f"Search Query: '{query}'")
    print(f"Max Pages: {max_pages}")
    print(f"Max Jobs to Display: {max_jobs}")
    print("-" * 30)

    for page_num in range(max_pages):
        if jobs_processed_count >= max_jobs:
            print(f"\nReached maximum job limit ({max_jobs}). Stopping.")
            break

        print(f"\nFetching search results page {page_num + 1}...")
        # Construct URL: page 0 is base, subsequent pages use /fpn/ offset
        page_url = base_search_url if page_num == 0 else f"{base_search_url}/fpn/{page_num * 20}"

        response = fetch_page(page_url)
        if response is None:
            print(f"Failed to fetch page {page_num + 1}. Moving to next or stopping.")
            continue # Skip to next page if fetch fails

        soup = BeautifulSoup(response.text, "html.parser")

        # --- Extract JSON data from the script tag ---
        script_tag_content = None
        for script in soup.find_all("script"):
            if script.string and "var apResp" in script.string:
                script_tag_content = script.string
                break

        if not script_tag_content:
            print(f"Could not find the 'apResp' script tag on page {page_num + 1}. Skipping page.")
            # You might want to save the HTML here for debugging if needed:
            # with open(f"rozee_page_{page_num + 1}_debug.html", "w", encoding="utf-8") as f:
            #     f.write(response.text)
            continue

        # Use regex to find the JSON part after 'var apResp ='
        match = re.search(r"var\s+apResp\s*=\s*({.*?});?\s*$", script_tag_content, re.DOTALL | re.MULTILINE)
        if not match:
            print(f"Could not extract JSON data using regex from script on page {page_num + 1}. Skipping page.")
            continue

        json_str = match.group(1)

        # Clean potential trailing commas before closing braces/brackets (common issue)
        json_str_cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)

        try:
            apResp_data = json.loads(json_str_cleaned)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON data on page {page_num + 1}: {e}")
            # Debugging: print the problematic string part
            # print("Problematic JSON String Snippet:", json_str_cleaned[:500] + "...")
            continue

        # --- Process Jobs from JSON ---
        jobs_on_page = []
        response_data = apResp_data.get("response", {})
        job_lists = response_data.get("jobs", {})
        sponsored_jobs = job_lists.get("sponsored", [])
        basic_jobs = job_lists.get("basic", [])
        jobs_on_page.extend(sponsored_jobs)
        jobs_on_page.extend(basic_jobs)

        if not jobs_on_page:
            print(f"No jobs found in the JSON data on page {page_num + 1}. Stopping search.")
            break

        print(f"Found {len(jobs_on_page)} potential job listings on page {page_num + 1}.")

        for job_data in jobs_on_page:
            if jobs_processed_count >= max_jobs:
                print(f"\nReached maximum job limit ({max_jobs}) while processing page. Stopping.")
                break # Break inner loop

            job_details = {}
            job_details["job_title"] = job_data.get("title", "N/A")
            job_details["company_name"] = job_data.get("company", "N/A")
            job_details["location"] = job_data.get("city", "N/A")
            job_details["employment_type"] = job_data.get("type", "N/A")
            job_details["experience_required"] = job_data.get("experience_text", "N/A")
            job_details["job_link"] = "https://www.rozee.pk/" + job_data.get("permaLink", "")

            # Format date (optional, basic handling)
            raw_date = job_data.get("created_at", "")
            formatted_date = "N/A"
            if raw_date:
                try:
                    # Handle ISO 8601 format (common in APIs)
                    dt_obj = datetime.fromisoformat(raw_date.replace("Z", "+00:00")) # Make timezone aware if needed
                    formatted_date = dt_obj.strftime("%Y-%m-%d") # Simple YYYY-MM-DD format
                except ValueError:
                    formatted_date = raw_date # Fallback to raw string if parsing fails

            job_details["date_posted"] = formatted_date

            # --- Fetch and Parse Job Detail Page ---
            print(f"  Fetching details for: {job_details['job_title']} ({job_details['job_link']})")
            detail_response = fetch_page(job_details["job_link"])
            description = "N/A"
            if detail_response:
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")
                # Rozee.pk uses an element with id='jbDetail' for the main description
                description_div = detail_soup.find("div", id="jbDetail")
                if description_div:
                    # Get text content, stripping extra whitespace and joining lines
                    description = description_div.get_text(separator="\n", strip=True)
                else:
                    description = "Could not find description div."
            else:
                description = "Failed to fetch detail page."

            job_details["description"] = description

            scraped_jobs_data.append(job_details)
            jobs_processed_count += 1

            # Display job details immediately
            print("\n" + "="*40)
            print(f"Job Title:    {job_details['job_title']}")
            print(f"Company:      {job_details['company_name']}")
            print(f"Location:     {job_details['location']}")
            print(f"Date Posted:  {job_details['date_posted']}")
            print(f"Experience:   {job_details['experience_required']}")
            print(f"Type:         {job_details['employment_type']}")
            print(f"Link:         {job_details['job_link']}")
            print("\n--- Description Snippet ---")
            # Display only the first 200 characters of the description
            desc_snippet = job_details['description'][:200].strip()
            print(desc_snippet + ("..." if len(job_details['description']) > 200 else ""))
            print("="*40 + "\n")

            # Respectful delay
            print(f"--- Processed {jobs_processed_count}/{max_jobs} jobs ---")
            time.sleep(DELAY_BETWEEN_DETAILS)

        # Check again if we need to break the outer loop
        if jobs_processed_count >= max_jobs:
            break

        # Respectful delay between fetching search result pages
        print(f"--- Waiting {DELAY_BETWEEN_PAGES}s before next page ---")
        time.sleep(DELAY_BETWEEN_PAGES)

    print(f"\n--- Scraping Finished ---")
    print(f"Total job details displayed: {jobs_processed_count}")
    if not scraped_jobs_data:
        print("No jobs were successfully scraped and processed.")

# --- Main Execution ---

if __name__ == "__main__":
    scrape_and_display_rozee(
        query=SEARCH_QUERY,
        max_pages=MAX_PAGES_TO_SCRAPE,
        max_jobs=MAX_JOBS_TO_PROCESS
    )
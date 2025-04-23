import streamlit as st
from groq import Groq
import requests
from pyairtable import Table
import json
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# Airtable Configuration
AIRTABLE_BASE_ID = "appEe8wbaC0R6HSFs"
WEBSITES_TABLE = "websites"
CAMPAIGNS_TABLE = "campaigns_table"

# Fetch record ID from URL
query_params = st.query_params
record_id = query_params.get("record_id")

if not record_id:
    st.error("Missing record_id in the URL parameters.")
    st.stop()

st.info(f"Fetched Record ID: {record_id}")

# ✅ Fetch website record from Airtable
def get_airtable_record(record_id):
    """Fetches the website record from Airtable."""
    try:
        websites_table = Table(
            "patMtGjL3ThJEfi7q.d29e0e83fd0d570fec72e7a19205423f1afa9630058dd7f1bdc116fbd8b6e771",
            AIRTABLE_BASE_ID, WEBSITES_TABLE
        )
        record = websites_table.get(record_id)

        if record:
            st.success("✅ Website record fetched successfully!")
            return record
        else:
            st.error("❌ No record found.")
            st.stop()

    except Exception as e:
        st.error(f"❌ Airtable Connection Error: {e}")
        st.stop()

# ✅ Fetch existing campaigns
def get_existing_campaigns(record_id, airtable_api_key):
    """Fetches existing campaign names associated with the website record."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CAMPAIGNS_TABLE}"
    headers = {"Authorization": f"Bearer {airtable_api_key}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        st.error(f"Failed to fetch existing campaigns: {response.text}")
        return []

    existing_campaigns = []
    records = response.json().get("records", [])

    for record in records:
        fields = record.get("fields", {})
        if fields.get("website_record_id") == record_id:
            existing_campaigns.append(fields.get("campaign_name"))

    return existing_campaigns

def generate_json_sequences(email_sequences_prompt,topic, llm_api_key):
    """Generates JSON sequences for email and LinkedIn campaigns."""

    st.info(f"Generating sequences for: {topic}")
    st.info(f"{email_sequences_prompt}")

    # Email JSON sequence prompt
    email_prompt = f"{email_sequences_prompt} {topic}"


    # LinkedIn JSON sequence prompt
    linkedin_prompt = f"""
    Create a 3-part LinkedIn post series for the topic below in **valid JSON format only** with no comments.
    Output must start and end with `[` and `]`.

    **Topic:** {topic}

    **JSON Format:**
    [
    {{"content": "First LinkedIn post with CTA"}},
    {{"content": "Second LinkedIn post with insights"}},
    {{"content": "Third LinkedIn post with a strong CTA"}}
    ]
    """

    # Generate JSON sequences
    email_json = generate_text(email_prompt, llm_api_key)
    linkedin_json = generate_text(linkedin_prompt, llm_api_key)

    try:
        email_data = json.loads(email_json)
        linkedin_data = json.loads(linkedin_json)
    except Exception as e:
        st.error(f"Invalid JSON format: {e}")
        return None, None

    return json.dumps(email_data), json.dumps(linkedin_data)

# ✅ LLM Text Generation
def generate_text(prompt, api_key):
    """Generates text using Groq with error handling."""
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": "You are a Marketing Strategist."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        st.info(response)
        if response and response.choices:
            return response.choices[0].message.content.strip()

        
    except Exception as e:
        st.error(f"❌ Groq Generation Error: {e}")
        return None

# ✅ Fetch and parse sitemap
def fetch_urls_from_sitemap(sitemap_url):
    """
    Extracts all URLs from a sitemap and returns them as a list.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(sitemap_url, headers=headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'xml')
            urls = [loc.text for loc in soup.find_all('loc') if not loc.text.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))]
            return urls
        else:
            print(f"❌ Failed to fetch sitemap. Status Code: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Error fetching sitemap: {e}")
        return []

# Function to fetch and extract clean text content from a webpage
def fetch_page_content(url):
    """
    Fetches and extracts clean text content with proper encoding handling.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": url,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            print(f"❌ Failed to fetch page ({response.status_code}): {url}")
            return ""
        
        soup = BeautifulSoup(content, "html.parser")

        # Extract content
        headings = [h.get_text().strip() for h in soup.find_all(['h1', 'h2', 'h3'])]
        paragraphs = [p.get_text().strip() for p in soup.find_all('p')]

        content = "\n".join(headings + paragraphs)

        return content if content else "No content extracted."

    except Exception as e:
        print(f"❌ Exception occurred: {e}")
        return ""

def summarize_content(all_content, llm_api_key):
    """Summarizes the combined content from all pages."""
    if not all_content.strip() or "No meaningful content found" in all_content:
        st.warning("No meaningful content extracted from the sitemap.")
        return "No content available to summarize."

    st.info("Summarizing extracted content...")
    
    prompt = f"""
    You are a professional content summarizer.
    
    Summarize the following content into a concise, clear, and insightful overview:
    
    {all_content}
    
    Provide a detailed summary highlighting key points, product overviews, and relevant information.
    """
    
    summary = generate_text(prompt, llm_api_key)
    
    return summary if summary else "No summary generated."

def save_summary_to_airtable(record_id, summary, airtable_api_key):
    """Updates the page_parsed field in Airtable with the summarized content."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{WEBSITES_TABLE}/{record_id}"
    headers = {"Authorization": f"Bearer {airtable_api_key}", "Content-Type": "application/json"}

    data = {"fields": {"page_parsed": summary}}

    response = requests.patch(url, headers=headers, json=data)

    if response.status_code == 200:
        st.success("✅ Summary saved to Airtable successfully.")
    else:
        st.error(f"❌ Failed to save summary: {response.text}")

# ✅ Generate new, unique campaign topics
def generate_campaign_topics(campaign_generation_prompt, page_parsed, llm_api_key, existing_campaigns):
    """Generates new campaign topics, avoiding duplicates."""

    existing_campaigns_str = "\n".join(existing_campaigns) if existing_campaigns else "None"

    prompt = f"""
    {campaign_generation_prompt}
    {page_parsed}

    Here are the existing campaigns that you should NOT generate again:
    {existing_campaigns_str}

    Generate only **new, unique campaign topics** not in the above list.
    Only provide topic names, one per line, with no additional details.
    """
    
    topics_text = generate_text(prompt, llm_api_key)

    if not topics_text:
        return []

    # Extract unique topics
    topics = []
    pattern = r"^(?:[-•*]|\d+\.|Topic:)\s*(.*)"

    for line in topics_text.splitlines():
        line = line.strip()

        if not line or "here are" in line.lower():
            continue

        match = re.match(pattern, line)
        if match:
            topic = match.group(1).strip()

            if topic and topic not in existing_campaigns:
                topics.append(topic)

    return topics
def update_websites_table(record_id, airtable_api_key):
    """Updates websites_table with campaign_generated = 'yes'."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{WEBSITES_TABLE}/{record_id}"
    headers = {"Authorization": f"Bearer {airtable_api_key}", "Content-Type": "application/json"}

    data = {"fields": {"campaign_generated": "Yes"}}

    response = requests.patch(url, headers=headers, json=data)

    if response.status_code == 200:
        st.success("Campaign status updated to 'yes'")
    else:
        st.error(f"Failed to update campaign status: {response.text}")

# ✅ Save new campaigns to Airtable
def save_to_airtable(campaigns, airtable_api_key, record_id):
    """Saves generated campaigns to Airtable."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{CAMPAIGNS_TABLE}"
    headers = {
        "Authorization": f"Bearer {airtable_api_key}",
        "Content-Type": "application/json"
    }

    for campaign in campaigns:
        data = {
            "fields": {
                "website_record_id": record_id,
                "campaign_name": campaign["campaign_name"],
                "email_sequences": campaign["email_sequences"],
                "linkedin_sequences": campaign["linkedin_sequences"]
            }
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 200:
            st.success(f"Saved: {campaign['campaign_name']}")
        else:
            st.error(f"Failed to save {campaign['campaign_name']}: {response.text}")

# ✅ Main Execution
st.title("Automated Campaign Generator")

record = get_airtable_record(record_id)
fields = record.get("fields", {})

airtable_api_key = fields.get("airtable_api_key", "")
llm_api_key = fields.get("llm_api_key", "")
sitemap_url = fields.get("website_url", "")
campaign_generation_prompt = fields.get("campaign_generation_prompt")
email_sequences_prompt = fields.get("email_sequences_prompt")
campaign_generated = fields.get("campaign_generated", "")
page_parsed = fields.get("page_parsed", "")

# Fetch and summarize sitemap content
if campaign_generated == "No":
    urls = fetch_urls_from_sitemap(sitemap_url)

    if urls:
        st.info(f"{len(urls)} URLs found. Extracting content from the URLs...\n")
    urls = urls[:5]
    all_content = ""
    for idx, url in enumerate(urls, start=1):
        content = fetch_page_content(url)
        st.info(content)
        if len(all_content.split()) < 1000:
            all_content += f"\n---\nContent from {url}:\n{content}\n"

    st.info("\n Extraction complete!")
    summary = summarize_content(all_content, llm_api_key)
    save_summary_to_airtable(record_id, summary, airtable_api_key)
else:
    st.info("Page content already parsed and summarized.")

existing_campaigns = get_existing_campaigns(record_id, airtable_api_key)
topics = generate_campaign_topics(campaign_generation_prompt, page_parsed, llm_api_key, existing_campaigns)

campaigns = []
for topic in topics:
    email_json, linkedin_json = generate_json_sequences(email_sequences_prompt,topic, llm_api_key)
    
    if email_json and linkedin_json:
        campaigns.append({
            "campaign_name": topic,
            "email_sequences": email_json,
            "linkedin_sequences": linkedin_json
        })

if campaigns:
    save_to_airtable(campaigns, airtable_api_key, record_id)
    update_websites_table(record_id, airtable_api_key)
else:
    st.info("No new campaigns generated.")

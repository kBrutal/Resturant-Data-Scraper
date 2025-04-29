import json
import os
import requests
import argparse
import time
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

def extract(json_file_path):
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Extract restaurant data using Groq API')
    parser.add_argument('--api-key', help='Your Groq API key')
    parser.add_argument('--batch-size', type=int, default=1, help='Number of URLs to process per batch')
    parser.add_argument('--delay', type=float, default=5.0, help='Delay between API calls in seconds')
    args = parser.parse_args()
    
    # Try to get API key from command line argument first
    GROQ_API_KEY = args.api_key
    
    # If not provided via command line, try to load from environment
    if not GROQ_API_KEY:
        # Load from .env file if it exists
        load_dotenv()
        GROQ_API_KEY = os.getenv('GROQ_API_KEY')
    
    # Still no API key? Show an error
    if not GROQ_API_KEY:
        print("Error: Groq API key not found. Please provide it using one of these methods:")
        print("1. Command line argument: --api-key YOUR_API_KEY")
        print("2. Environment variable: GROQ_API_KEY=your_key")
        print("3. .env file with GROQ_API_KEY=your_key")
        return
    
    # Load the JSON data from the provided file path
    json_data = load_json_data(json_file_path)
    if not json_data:
        print(f"Failed to load JSON data from {json_file_path}")
        return
    
    # Process the data in chunks by URL
    all_results = []
    batch_size = args.batch_size
    delay_between_calls = args.delay
    
    # Get all URLs
    urls = list(json_data.keys())
    
    # Initialize token tracking
    max_tokens_per_minute = 6000  # Default Groq limit
    tokens_used = 0
    window_start = time.time()
    
    # Process in batches
    for i in range(0, len(urls), batch_size):
        batch_urls = urls[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(len(urls) + batch_size - 1)//batch_size}")
        
        # Create a subset of the JSON data for this batch
        batch_data = {url: json_data[url] for url in batch_urls}
        
        # Extract text for this batch
        text_content = extract_text_from_json(batch_data)
        
        # Estimate tokens for this request
        estimated_tokens = estimate_tokens(text_content) + 200  # Add buffer for prompt
        
        # Check if we need to wait before making the next request
        current_time = time.time()
        if current_time - window_start < 60:  # Within same minute
            if tokens_used + estimated_tokens > max_tokens_per_minute:
                wait_time = 60 - (current_time - window_start) + 1  # Add 1 second buffer
                print(f"Approaching token limit. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                tokens_used = 0
                window_start = time.time()
        else:
            tokens_used = 0
            window_start = time.time()
        
        # Call Groq API with retry mechanism
        extracted_data = call_groq_llama(text_content, GROQ_API_KEY)
        tokens_used += estimated_tokens
        
        if extracted_data:
            try:
                # Parse the JSON response
                result = json.loads(extracted_data)
                all_results.append(result)
            except json.JSONDecodeError:
                print(f"Failed to parse JSON from batch {i//batch_size + 1}")
                print("Raw response:", extracted_data[:200] + "...")  # Print first 200 chars
        
        # Add delay between batches if not the last batch
        if i + batch_size < len(urls) and delay_between_calls > 0:
            time.sleep(delay_between_calls)
    
    # Combine results from all batches
    combined_result = combine_results(all_results)
    
    # Save combined results
    if combined_result:
        save_extracted_data(combined_result)
    else:
        print("Failed to extract data or combine results")

def load_json_data(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            return json.load(file)
    except json.JSONDecodeError:
        # If the file isn't valid JSON, try to extract JSON from a text file
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
            # Find JSON content between curly braces
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                json_content = content[start:end]
                return json.loads(json_content)
    except Exception as e:
        print(f"Error loading JSON data from {filename}: {e}")
        return None

def extract_text_from_json(data):
    all_text = ""
    for url, page_data in data.items():
        all_text += f"URL: {url}\n"
        all_text += f"Title: {page_data.get('title', 'No title')}\n"
        all_text += f"Content: {page_data.get('text', 'No content')}\n\n"
    return all_text

def estimate_tokens(text):
    # Rough estimation: 1 token ~= 4 characters in English
    return len(text) // 4

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def call_groq_llama(text_data, api_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    Extract the following information from this restaurant website data:
    
    1. Restaurant name and location (full address) if present
    2. Menu items with descriptions (no need for prices if not available) if present
    3. Special features (e.g., vegetarian options marked as [v], gluten-free options marked as [gf], etc.) if present
    4. Operating hours and contact information if present
    5. Provide extra relevant information if available
    
    Format the response as a structured JSON with these keys (include only if information is found): 
    "restaurant_name", "location", "menu_items" (as an array of objects with "name" and "description"), 
    "special_features" (as an array), "hours" (as an object with days as keys), "contact_info"
    
    Website data:
    {text_data}
    
    Only return the JSON object, nothing else.
    """
    
    data = {
        "model": "llama3-70b-8192",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that extracts restaurant information from website data and formats it as JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4000
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        # Check for rate limit in successful response
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 10))
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            raise requests.exceptions.RequestException("Rate limited")
            
        response.raise_for_status()
        
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 429:
                error_data = e.response.json()
                if 'Please try again in' in error_data.get('error', {}).get('message', ''):
                    wait_time = float(error_data['error']['message'].split('in ')[1].split('s')[0])
                    print(f"Rate limited. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
        raise  # Re-raise the exception for the retry decorator

def combine_results(results_list):
    if not results_list:
        return None
    
    # Initialize combined result with the first result
    combined = results_list[0]
    
    # For each additional result, merge with combined
    for result in results_list[1:]:
        # Restaurant name and location (take the non-empty one)
        if not combined.get('restaurant_name') and result.get('restaurant_name'):
            combined['restaurant_name'] = result['restaurant_name']
        
        if not combined.get('location') and result.get('location'):
            combined['location'] = result['location']
        
        # Menu items (append unique items)
        if result.get('menu_items'):
            if not combined.get('menu_items'):
                combined['menu_items'] = []
            
            # Get existing item names for deduplication
            existing_names = {item['name'] for item in combined['menu_items']}
            
            # Add only unique items
            for item in result['menu_items']:
                if item['name'] not in existing_names:
                    combined['menu_items'].append(item)
                    existing_names.add(item['name'])
        
        # Special features (append unique features)
        if result.get('special_features'):
            if not combined.get('special_features'):
                combined['special_features'] = []
            
            # Add only unique features
            for feature in result['special_features']:
                if feature not in combined['special_features']:
                    combined['special_features'].append(feature)
        
        # Hours (take the most detailed one)
        if result.get('hours'):
            if not combined.get('hours') or len(result['hours']) > len(combined['hours']):
                combined['hours'] = result['hours']
        
        # Contact info (take the most detailed one)
        if result.get('contact_info'):
            if not combined.get('contact_info'):
                combined['contact_info'] = result['contact_info']
            elif isinstance(result['contact_info'], dict) and isinstance(combined['contact_info'], dict):
                combined['contact_info'].update(result['contact_info'])
    
    return combined

def save_extracted_data(data, filename="resturant_info_extracted.json"):
    try:
        # If data is already a dict, no need to parse
        if isinstance(data, dict):
            parsed_json = data
        else:
            # Otherwise try to parse as JSON
            parsed_json = json.loads(data)
        
        with open(filename, 'w', encoding='utf-8') as file:
            json.dump(parsed_json, file, indent=2)
        print(f"Extracted data saved to {filename}")
        
        # Print a summary of what was extracted
        print("\nExtraction Summary:")
        if 'restaurant_name' in parsed_json:
            print(f"Restaurant: {parsed_json['restaurant_name']}")
        
        if 'menu_items' in parsed_json:
            print(f"Menu Items: {len(parsed_json['menu_items'])} items extracted")
        
        if 'special_features' in parsed_json:
            print(f"Special Features: {len(parsed_json['special_features'])} features identified")
        
        if 'hours' in parsed_json:
            print(f"Hours: Information for {len(parsed_json['hours'])} days extracted")
        
        if 'contact_info' in parsed_json:
            print("Contact Information: ✓")
            
    except Exception as e:
        print(f"Error saving extracted data: {e}")
        if not isinstance(data, dict):
            print("Raw data:", data[:200] + "...")  # Print first 200 chars if not a dict

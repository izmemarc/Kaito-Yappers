import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any
import openai
import logging
import re
from cache_manager import CacheManager

logger = logging.getLogger(__name__)

cache = CacheManager("report_fixes_cache.json")

def validate_report(content: str) -> list:
    """Validate report format and username-URL matches."""
    errors = []
    
    if not content.startswith("# Kaito Yapper Analysis Report"):
        errors.append("Missing or incorrect title")
    
    sections = content.split("###")[1:]
    
    for section in sections:
        if not section.strip():
            continue
            
        try:
            # Extract username and percentage
            header = section.split('\n')[0]
            if '|' not in header:
                errors.append(f"Invalid section header format: {header}")
                continue
                
            username, percentage = header.split('|')
            username = username.strip().lower()
            
            # Validate percentage
            try:
                percentage = float(percentage.strip().replace('%', ''))
                if not (0 <= percentage <= 100):
                    errors.append(f"Invalid percentage for {username}: {percentage}%")
            except ValueError:
                errors.append(f"Invalid percentage format for {username}")
            
            # Check tweet URLs match username
            urls = re.findall(r'\[(?:link|Link|source|Source|View Tweet)\]\((https://[^)]+)\)', section)
            for url in urls:
                if f"x.com/{username}/" not in url.lower() and f"twitter.com/{username}/" not in url.lower():
                    errors.append(f"URL {url} doesn't match username {username}")
            
            # Check for bullet points
            bullets = [line for line in section.split('\n') if line.strip().startswith('-')]
            if not bullets:
                errors.append(f"No bullet points found for {username}")
            
            # Check for retweets
            for bullet in bullets:
                if bullet.lower().startswith('- rt @'):
                    errors.append(f"Found retweet in {username}'s section: {bullet}")
            
            # Verify quoted tweet exists
            quoted_tweets = [line for line in bullets if '"' in line or '"' in line]
            if not quoted_tweets:
                errors.append(f"No quoted tweet found for {username}")
                
        except Exception as e:
            errors.append(f"Error processing section: {str(e)}")
    
    return errors

def save_raw_report(content: str) -> str:
    """Save the raw report content to a file."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'reports/raw_report_{timestamp}.md'
    os.makedirs('reports', exist_ok=True)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filename

async def fix_report_with_gpt(content: str) -> str:
    """Use GPT-4o mini to fix formatting issues in the report."""
    # Check cache first
    cache_key = hash(content)
    cached_result = cache.get(str(cache_key))
    if cached_result:
        return cached_result
    
    prompt = """You are a precise report validator. Fix this Kaito Yapper Analysis Report by:

1. For each section, verify the username in the URL matches the section header
2. Only keep tweets where the URL contains the correct username
3. Remove any tweets where the URL doesn't match the section's username
4. Format each section as:
   ### username | X.XX%
   - original tweet content [link](URL)
   - original tweet content [link](URL)
   - original tweet content [link](URL)
   
   - "Most important tweet quoted exactly" [Link](URL)

5. Remove any retweets (RT @)
6. Ensure each URL contains the username from its section header
7. Keep sections ordered by percentage (highest to lowest)

Original report:
{content}
"""
    
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": "You are a precise report validator that ensures usernames match their tweet URLs."
            },
            {
                "role": "user",
                "content": prompt.format(content=content)
            }],
            max_tokens=4000,
            temperature=0
        )
        
        # Cache the result before returning
        if response:
            fixed_content = response.choices[0].message['content']
            cache.set(str(cache_key), fixed_content)
            return fixed_content
        return content
    except Exception as e:
        logger.error(f"Error using GPT to fix report: {str(e)}")
        return content

async def process_report(content: str) -> Dict[str, Any]:
    """Process and validate report, fixing issues with GPT if needed."""
    # First validate the report
    errors = validate_report(content)
    
    # If there are errors, try to fix with GPT
    if errors:
        logger.info(f"Found {len(errors)} formatting issues, attempting to fix with GPT")
        content = await fix_report_with_gpt(content)
        # Validate again after fixing
        errors = validate_report(content)
    
    if errors:
        return {
            'success': False,
            'errors': errors
        }
    
    # Save raw report
    try:
        raw_file = save_raw_report(content)
        return {
            'success': True,
            'raw_file': raw_file
        }
    except Exception as e:
        return {
            'success': False,
            'errors': [f"Error saving report: {str(e)}"]
        }

async def main():
    """Main async function to process report."""
    # Example usage
    with open('your_report.txt', 'r', encoding='utf-8') as f:
        report_content = f.read()
    
    result = await process_report(report_content)
    if result['success']:
        print(f"Report processed successfully. Raw file saved to: {result['raw_file']}")
    else:
        print("Validation errors found:")
        for error in result['errors']:
            print(f"- {error}")

if __name__ == "__main__":
    # Proper asyncio setup for Windows compatibility
    if os.name == 'nt':  # Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Run the async main function
    asyncio.run(main())

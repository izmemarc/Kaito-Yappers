import json
import os
from datetime import datetime
from typing import Dict, Any

def validate_report(content: str) -> list:
    errors = []
    
    # Check if content starts with title
    if not content.startswith("# Kaito Yapper Analysis Report"):
        errors.append("Missing or incorrect title")
    
    # Parse sections
    sections = content.split("###")[1:]  # Skip the header
    
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
            username = username.strip()
            
            # Validate percentage format
            try:
                percentage = float(percentage.strip().replace('%', ''))
                if not (0 <= percentage <= 100):
                    errors.append(f"Invalid percentage for {username}: {percentage}%")
            except ValueError:
                errors.append(f"Invalid percentage format for {username}")
            
            # Check for bullet points
            bullets = [line for line in section.split('\n') if line.strip().startswith('-')]
            if not bullets:
                errors.append(f"No bullet points found for {username}")
            
            # Check for retweets
            for bullet in bullets:
                if bullet.lower().startswith('- rt @'):
                    errors.append(f"Found retweet in {username}'s section: {bullet}")
            
            # Check for link
            if '[Link]' not in section and '[View Tweet]' not in section:
                errors.append(f"No link found for {username}")
                
        except Exception as e:
            errors.append(f"Error processing section: {str(e)}")
    
    return errors

def save_raw_report(content: str) -> str:
    # Create raw_reports directory if it doesn't exist
    os.makedirs('raw_reports', exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'raw_reports/report_{timestamp}.json'
    
    # Convert report to JSON format
    report_dict = {
        'timestamp': timestamp,
        'content': content,
        'sections': []
    }
    
    # Parse sections
    sections = content.split("###")[1:]  # Skip the header
    for section in sections:
        if not section.strip():
            continue
            
        try:
            lines = section.split('\n')
            header = lines[0]
            username, percentage = header.split('|')
            
            # Get bullets excluding retweets
            bullets = [line.strip() for line in lines 
                      if line.strip().startswith('-') and not line.lower().strip().startswith('- rt @')]
            
            section_dict = {
                'username': username.strip(),
                'percentage': float(percentage.strip().replace('%', '')),
                'bullets': bullets,
                'link': next((line for line in lines if '[Link]' in line or '[View Tweet]' in line), '')
            }
            
            report_dict['sections'].append(section_dict)
            
        except Exception as e:
            print(f"Error processing section for JSON: {str(e)}")
    
    # Save as JSON
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)
    
    return filename

def process_report(content: str) -> Dict[str, Any]:
    # First validate the report
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
            'errors': [f"Error saving raw report: {str(e)}"]
        }

if __name__ == "__main__":
    # Example usage
    with open('your_report.txt', 'r', encoding='utf-8') as f:
        report_content = f.read()
    
    result = process_report(report_content)
    if result['success']:
        print(f"Report processed successfully. Raw file saved to: {result['raw_file']}")
    else:
        print("Validation errors found:")
        for error in result['errors']:
            print(f"- {error}")

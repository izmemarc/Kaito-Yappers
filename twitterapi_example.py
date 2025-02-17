import requests
import json

url = "https://api.twitterapi.io/twitter/user/last_tweets"
querystring = {"userName": "as131"}
headers = {"X-API-Key": "<api-key>"}

try:
    response = requests.get(url, headers=headers, params=querystring)
    response.raise_for_status()  # Raises an error for bad status codes
    data = response.json()       # Parse JSON response

    # Pretty-print the response JSON
    print(json.dumps(data, indent=2))
except requests.exceptions.RequestException as e:
    print(f"Request error: {e}") 
import aiohttp
import logging
from typing import List, Dict, Any
import asyncio
import json

logger = logging.getLogger(__name__)

class TwitterScraper:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.cache = {}
        self.base_url = "https://api.twitterapi.io/twitter"
        self.headers = {
            "X-API-Key": api_key,
            "Accept": "application/json"
        }

    async def get_user_tweets(self, username: str) -> List[Dict]:
        """Get recent tweets for a user using TwitterAPI.io"""
        try:
            if not username or not self.api_key:
                logger.warning(f"Missing username or API key for {username}")
                return []

            url = f"{self.base_url}/user/last_tweets"
            params = {
                "userName": username
            }

            logger.info(f"Making request to {url} for user {username}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    response_text = await response.text()
                    logger.info(f"Response status: {response.status}")

                    if response.status == 401:
                        logger.error(f"TwitterAPI.io authentication failed for {username}. Response: {response_text}")
                        return []
                    elif response.status != 200:
                        logger.error(f"Error {response.status} getting tweets for {username}. Response: {response_text}")
                        return []
                    
                    try:
                        data = json.loads(response_text)
                        # Extract tweets from the nested structure
                        if (isinstance(data, dict) and 
                            data.get('status') == 'success' and 
                            isinstance(data.get('data'), dict)):
                            
                            all_tweets = data['data'].get('tweets', [])
                            # Filter out retweets and ensure author matches username
                            tweets = [
                                tweet for tweet in all_tweets 
                                if 'retweetedTweet' not in tweet 
                                and tweet.get('author', {}).get('userName', '').lower() == username.lower()
                            ]
                            logger.info(f"Successfully retrieved {len(tweets)} original tweets (filtered from {len(all_tweets)} total) for {username}")
                            if tweets:
                                self.cache[username] = tweets
                            return tweets
                        else:
                            logger.error(f"Unexpected data format for {username}. Response structure: {json.dumps(data)[:200]}...")
                            return []
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response for {username}: {e}")
                        return []

        except Exception as e:
            logger.error(f"Error scraping {username}: {str(e)}", exc_info=True)
            return []

    async def scrape_multiple_users(self, usernames: List[str]) -> None:
        """Scrape tweets from multiple users concurrently"""
        tasks = [self.get_user_tweets(username) for username in usernames]
        await asyncio.gather(*tasks)

    def get_cached_data(self, timestamp: str = None) -> Dict[str, Any]:
        """Get cached data for a specific timestamp or latest"""
        if not self.cache:
            logger.warning("Cache is empty")
            return {}
            
        if timestamp:
            return {
                k: v for k, v in self.cache.items() 
                if k.endswith(timestamp)
            }
        else:
            # Get latest timestamp
            timestamps = set(k.split('_')[-1] for k in self.cache.keys())
            if not timestamps:
                return {}
            latest = max(timestamps)
            return {
                k: v for k, v in self.cache.items() 
                if k.endswith(latest)
            } 
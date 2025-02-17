import asyncio
import os
from dotenv import load_dotenv
from twitter_scraper import TwitterScraper
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_twitter_api():
    load_dotenv()
    api_key = os.getenv('TWITTER_API_KEY')
    
    if not api_key:
        logger.error("TWITTER_API_KEY not found in environment variables")
        return
        
    scraper = TwitterScraper(api_key)
    test_user = "VitalikButerin"
    
    # Test tweet retrieval
    tweets = await scraper.get_user_tweets(test_user)
    if tweets:
        logger.info(f"Successfully retrieved {len(tweets)} tweets for {test_user}")
        logger.info(f"First tweet: {tweets[0]}")
    else:
        logger.error("Failed to retrieve tweets")

if __name__ == "__main__":
    asyncio.run(test_twitter_api()) 
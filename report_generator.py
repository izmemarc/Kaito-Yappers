import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import openai
import logging
import re
from validate_report import save_raw_report

logger = logging.getLogger(__name__)
class ReportGenerator:
    TWEET_SYSTEM_PROMPT = """You are analyzing tweets to create impactful summaries in Sandra's style (@sandraaleow).

Guidelines:
- Select only **3 at most significant tweets related to crypto**, ignoring personal updates, opinions, jokes, and non-newsworthy discussions.
- Prioritize **major announcements, partnerships, protocol upgrades, regulatory updates, and critical market movements**.
- **Exclude general takes, speculation, humor, and non-actionable insights**.
- Do not include duplicate tweets—each tweet should provide unique value.
- Format each point as a **single-line bullet point** with a clear takeaway.
- Include the **link to the most impactful tweet** at the end.
"""



    TWEET_USER_PROMPT = """Your goal is to create a concise, news-style summary of @{username}'s three most impactful tweets, strictly focusing on newsworthy content.

Guidelines:
Select and directly quote the three most news-relevant tweets from @{username}.
Prioritize major announcements, partnerships, industry insights, or significant developments.
Exclude tweets containing personal opinions, self-promotion, speculation, casual commentary, or engagement-bait.
Do not alter or paraphrase key details—maintain original wording for accuracy.
Embed the tweet link in the quoted text to ensure direct access to the source.
Ignore irrelevant content—if there are fewer than three qualifying tweets, do not force inclusions.
Remove irrelevant characters letters or symbols to the news itself
Remove emojis 
Remove hashtags 
Remove phrases like "breaking news" or "latest update"
Truncate or remove the non important parts of the tweet

Their tweets:
{tweets}"""

    def __init__(self, api_key: str, model: str = "gpt-4-0125-preview", max_tokens: int = 4000, temperature: float = 0.7):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.cache = {}
        
        # Initialize OpenAI API key
        openai.api_key = api_key

    def cleanup_temp_folders(self):
        """Clean up temporary data folders"""
        folders_to_clean = ['twitter_data', 'processed_data', 'cache']
        for folder in folders_to_clean:
            if os.path.exists(folder):
                for file in os.listdir(folder):
                    file_path = os.path.join(folder, file)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except Exception as e:
                        logger.error(f"Error deleting {file_path}: {e}")
                logger.info(f"Cleaned up {folder} directory")

    def process_tweets(self, tweets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process tweets to extract only essential information"""
        processed_tweets = []
        
        for tweet in tweets:
            # Skip replies
            if tweet.get('isReply', False):
                continue
            
            # Extract only essential fields
            processed_tweet = {
                'url': tweet.get('url', ''),
                'text': tweet.get('text', ''),
                'engagement': {
                    'likes': tweet.get('likeCount', 0),
                    'retweets': tweet.get('retweetCount', 0),
                    'replies': tweet.get('replyCount', 0),
                    'views': tweet.get('viewCount', 0)
                }
            }
            processed_tweets.append(processed_tweet)
        
        return processed_tweets

    async def analyze_user_tweets(self, username: str, tweets: List[Dict[str, Any]], rank: int) -> str:
        """Analyze tweets for a single user"""
        # Format tweets for prompt
        tweet_text = ""
        for tweet in tweets:
            # Skip retweets
            if tweet.get('isRetweet', False):
                continue
            tweet_text += f"\nTweet: {tweet['text']}"
            tweet_text += f"\nEngagement: {tweet['engagement']}"
            tweet_text += f"\nURL: {tweet['url']}\n"

        rank_desc = 'takes top1 yapper today' if rank == 1 else f'is at top {rank}'
        
        # Use the old format for OpenAI API calls
        response = await openai.ChatCompletion.acreate(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self.TWEET_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": self.TWEET_USER_PROMPT.format(
                        username=username,
                        rank=rank,
                        rank_desc=rank_desc,
                        tweets=tweet_text
                    )
                }
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        
        return response.choices[0].message['content']

    async def analyze_tweets(self, tweets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze tweets using OpenAI API"""
        # Get rankings from cache
        rankings = self.cache.get('rankings', [])
        if not rankings:
            raise Exception("No rankings data found in cache")

        # Group tweets by user
        user_tweets: Dict[str, List[Dict[str, Any]]] = {}
        ranked_usernames = [r['username'] for r in rankings]
        
        for tweet in tweets:
            username = tweet.get('author', {}).get('userName', 'unknown')
            if username == 'unknown' or username not in ranked_usernames:
                continue
                
            if username not in user_tweets:
                user_tweets[username] = []
            
            # Process tweet before adding
            processed_tweets = self.process_tweets([tweet])
            if processed_tweets:  # Only add if it's not a reply
                user_tweets[username].extend(processed_tweets)

        # Store processed tweets in cache
        self.cache['processed_tweets'] = user_tweets
        
    
        # Analyze each user's tweets (20 API calls)
        analyses = []
        logger.info(f"Processing {len(rankings)} users for trends analysis")
        
        for idx, ranking in enumerate(rankings, 1):
            username = ranking['username']
            logger.info(f"Analyzing tweets for user {idx}/{len(rankings)}: @{username}")
            if username in user_tweets:
                analysis = await self.analyze_user_tweets(username, user_tweets[username], idx)
                analyses.append(analysis)
            logger.info(f"Completed analysis for @{username}")

        self.cache['analyses'] = analyses

        return {
            'trends_analysis': analyses,
            'rankings': rankings
        }

    async def generate_full_report(self) -> str:
        """Generate a complete analysis report"""
        tweets = self.cache.get('tweets', {})
        if not tweets:
            logger.error("No tweet data found in cache")
            return self._generate_empty_report()

        # Combine all tweets into a single list
        all_tweets = []
        for username_tweets in tweets.values():
            all_tweets.extend(username_tweets)
        
        logger.info(f"Loaded {len(all_tweets)} tweets from cache")

        # Analyze tweets
        analysis = await self.analyze_tweets(all_tweets)

        # Ensure reports directory exists
        os.makedirs('reports', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f'reports/analysis_report_{timestamp}.md'

        # Create rankings lookup with score multiplied by 100
        rankings = {
            item['username']: {
                'rank': item['rank'],
                'score': item['score'] * 100  # Multiply by 100 for percentage
            } for item in analysis['rankings']
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# Kaito Yapper Analysis Report\n\n")
            f.write("What's Yappening\n\n")
            
            for idx, username in enumerate(sorted(rankings.keys(), key=lambda x: rankings[x]['rank'])):
                rank_info = rankings[username]
                f.write(f"### {username} | {rank_info['score']:.2f}%\n\n")

                seen_tweets = set()
    
                if idx < len(analysis['trends_analysis']):
                    user_analysis = analysis['trends_analysis'][idx]
                    lines = user_analysis.split('\n')

                    for line in lines:
                        if line.strip().startswith('-') and line not in seen_tweets:
                            # Skip retweets
                            if line.lower().strip().startswith('- rt @'):
                                continue
                            # Remove tweets containing "ont"
                            if "ont" in line.lower():
                                continue
                            # Remove quotation marks and fix hyperlink formatting
                            line = line.replace('"', '')
                            line = re.sub(r'\[.*?\]\s*\((https?://\S+?)\)\)', r'[\1]', line)
                            # Remove [word] at the end
                            line = re.sub(r'\[\w+\]$', '', line, flags=re.IGNORECASE).strip()
                            # Normalize case
                            line = line.capitalize()
                            f.write(f"{line}\n")
                            seen_tweets.add(line)

                    urls = [l for l in lines if 'https://' in l]
                    if urls:
                        f.write(f"\n{urls[0]}\n")

                else:
                    f.write("- No tweets available for analysis\n")

            f.write("\n---\n\n")

        # Read the generated report and save raw version
        with open(report_file, 'r', encoding='utf-8') as f:
            report_content = f.read()
        
        # Save raw report
        raw_report = save_raw_report(report_content)
        logger.info(f"Raw report saved to: {raw_report}")

        self.cleanup_temp_folders()
        logger.info(f"Report generated: {report_file}")
        return report_file
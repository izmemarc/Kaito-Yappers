import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Dict, Any, List
from dotenv import load_dotenv
import re
import html
import openai

# Telegram imports
import telegram
from telegram import Bot
from telegram.constants import ParseMode

# Import your analysis modules
from kaito_leaderboard import KaitoLeaderboard
from twitter_scraper import TwitterScraper
from report_generator import ReportGenerator
from validate_report import process_report

# -----------------------------------------------------------------------------
# Logging and Environment Setup
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kaito_report.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables first
load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

SCHEDULED_MODE = False  # Easy toggle for scheduled mode

def load_environment() -> Dict[str, Any]:
    """Load and validate environment variables."""
    required_vars = ['OPENAI_API_KEY', 'TWITTER_API_KEY', 'BOT_API_KEY', 'CHANNEL_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    return {
        'openai_api_key': os.getenv('OPENAI_API_KEY'),
        'twitter_api_key': os.getenv('TWITTER_API_KEY'),
        'bot_api_key': os.getenv('BOT_API_KEY'),
        'channel_id': os.getenv('CHANNEL_ID'),
        'model_name': os.getenv('MODEL_NAME', 'gpt-4o-mini'),
        'max_tokens': int(os.getenv('MAX_TOKENS', '4000')),
        'temperature': float(os.getenv('TEMPERATURE', '0.7')),
        'kaito_timeframe': os.getenv('KAITO_TIMEFRAME', '7d'),
        'run_time': os.getenv('RUN_TIME', '09:00')  # Default to 9 AM UTC+8
    }


def ensure_reports_directory():
    """Ensure that the 'reports' directory exists."""
    if not os.path.exists('reports'):
        os.makedirs('reports')
        logger.info("Created reports directory")


# -----------------------------------------------------------------------------
# TelegramSender Class
# -----------------------------------------------------------------------------

class TelegramSender:
    def __init__(self, bot_token: str):
        if not bot_token:
            raise ValueError("Bot token is required")
        self.bot = Bot(token=bot_token)

    async def send_message(self, channel_id: str, text: str) -> bool:
        """Send a message to a Telegram channel."""
        if not text or not channel_id:
            return False

        try:
            await self.bot.send_message(
                chat_id=channel_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            return False

    async def format_top_yappers(self, report_content: str) -> str:
        """Format the Top Yappers section with proper hyperlinks and date."""
        # Get the current date
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Format the header with the current date
        formatted_text = f"<b>Top Yappers as of {current_date}</b>\n\n"
        yappers = []

        for line in report_content.splitlines():
            if line.startswith('### ') and '|' in line:
                try:
                    # Extract the username
                    username = line[4:line.find('|')].strip()
                    # Extract the mindshare
                    mindshare = line.split('|')[1].strip()
                    if username and mindshare:
                        yappers.append((username, mindshare))
                except Exception as ex:
                    logger.error(f"Error parsing line for top yappers: {line} - {str(ex)}")
                    continue

        for idx, (username, mindshare) in enumerate(yappers[:20], 1):
            formatted_text += (
                f"{idx}. <a href='https://twitter.com/{username}'>"
                f"{html.escape(username)}</a> - {html.escape(mindshare)}\n"
            )

        return formatted_text

    async def format_whats_yappening(self, report_content: str) -> List[str]:
        """Format the What's Yappening section with HTML, ensuring no extra parentheses and splitting messages if needed."""
        messages = []
        formatted_text = "<b>What's Yappening</b>\n\n"

        # Find the start of the "What's Yappening" section
        start_idx = report_content.find("What's Yappening")
        if start_idx == -1:
            logger.error("Could not find What's Yappening section")
            return [formatted_text]

        # Find the end of the section, assuming "---" is a delimiter for sections
        end_idx = report_content.find("---", start_idx)
        if end_idx == -1:
            end_idx = len(report_content)  # If no delimiter, take till the end

        # Extract the content of the "What's Yappening" section
        content = report_content[start_idx:end_idx].strip()
        sections = content.split('### ')[1:]  # Split by headers

        current_message = formatted_text
        seen_tweets = set()  # To track and avoid duplicate tweets

        for section in sections:
            if not section.strip():
                continue

            header_end = section.find('\n')
            if header_end == -1:
                continue

            header = section[:header_end].strip()
            bullet_points = ""
            lines = section[header_end:].strip().splitlines()
            for line in lines:
                line = line.strip()
                if line.startswith('- '):
                    # Skip bullet points that do not contain a link.
                    if 'https://' not in line:
                        continue

                    # Analyze the content of the tweet using GPT-4o mini
                    if not await self.is_newsworthy_with_gpt(line):
                        continue

                    # Attempt to extract URL
                    match = re.search(r'https?://\S+', line)
                    if match:
                        url = match.group(0).rstrip(')')  # Remove trailing parenthesis if present
                        # Remove the URL and any surrounding parentheses from the line to use as display text
                        display_text = line.replace(url, '').replace('- ', '').strip()
                        # Remove any remaining parentheses and quotation marks
                        display_text = re.sub(r'[\(\)"""]', '', display_text).strip()

                        # Improve capitalization
                        display_text = display_text.capitalize()

                        # Remove bracketed words at the end of the tweet
                        display_text = re.sub(r'\s*\[.*?\]$', '', display_text)

                        # Check for duplicates
                        if display_text in seen_tweets:
                            continue
                        seen_tweets.add(display_text)

                        # Wrap the entire sentence in an HTML link
                        bullet_points += f"- <a href='{html.escape(url)}'>{html.escape(display_text)}</a>\n"

            if bullet_points:
                section_text = f"<b>{html.escape(header)}</b>\n\n{bullet_points}\n"
                # Check if adding this section would exceed Telegram's message limit
                if len(current_message) + len(section_text) > 4096:  # Telegram's message limit
                    messages.append(current_message)
                    current_message = section_text  # Start new message without "What's Yappening"
                else:
                    current_message += section_text

        if current_message:
            messages.append(current_message)

        return messages

    async def is_newsworthy_with_gpt(self, tweet: str) -> bool:
        """Use GPT-4o mini to analyze the tweet content and determine if it is newsworthy."""
        prompt = (
            f"Analyze the following tweet and determine if it is newsworthy, "
            f"providing context and relevance. Respond with 'newsworthy' if it contains "
            f"significant information or events, or 'not newsworthy' if it is out of context, "
            f"promotional, or lacks substantial content:\n\n{tweet}\n\n"
            "Respond with 'newsworthy' or 'not newsworthy'."
        )

        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0
            )
            result = response.choices[0].message['content'].strip().lower()
            return result == 'newsworthy'
        except Exception as e:
            logger.error(f"Error analyzing tweet with GPT: {str(e)}")
            return False  # Default to not newsworthy on error

    async def send_long_message(self, channel_id: str, text: str, chunk_size: int = 3800) -> bool:
        """Send a long message by splitting it into chunks."""
        if not text or not channel_id:
            return False

        chunks = []
        current_chunk = ""
        for line in text.splitlines():
            if len(current_chunk) + len(line) + 1 > chunk_size:
                chunks.append(current_chunk)
                current_chunk = line + '\n'
            else:
                current_chunk += line + '\n'
        if current_chunk:
            chunks.append(current_chunk)

        try:
            for chunk in chunks:
                await self.send_message(channel_id, chunk)
                await asyncio.sleep(1)  # Slight delay
            return True
        except Exception as e:
            logger.error(f"Failed to send message chunks: {str(e)}")
            return False


# -----------------------------------------------------------------------------
# Analysis Pipeline and Telegram Integration
# -----------------------------------------------------------------------------

async def run_analysis(config: Dict[str, Any]) -> None:
    """Run the complete analysis pipeline."""
    try:
        logger.info("Starting scheduled analysis run...")
        logger.info("Starting Kaito leaderboard processing...")
        kaito = KaitoLeaderboard(timeframe=config.get('kaito_timeframe', '7d'))
        top_20 = kaito.get_leaderboard()
        logger.info("Kaito data processed and cached")

        logger.info("Starting Twitter data scraping...")
        twitter = TwitterScraper(config['twitter_api_key'])
        usernames = [acc['username'] for acc in top_20]
        
        # Test API with first user and log detailed response
        test_user = usernames[0]
        logger.info(f"Testing Twitter API with user: {test_user}")
        test_tweets = await twitter.get_user_tweets(test_user)
        
        if not test_tweets:
            # Try a known good username as fallback
            fallback_user = "VitalikButerin"
            logger.info(f"Retrying with fallback user: {fallback_user}")
            test_tweets = await twitter.get_user_tweets(fallback_user)
            if not test_tweets:
                raise Exception(f"Twitter API authentication failed. Key: {config['twitter_api_key'][:10]}...")
        
        logger.info(f"Successfully tested Twitter API, proceeding with {len(usernames)} users")
        await twitter.scrape_multiple_users(usernames)
        
        if not twitter.cache:
            raise Exception("Failed to fetch any tweets after successful authentication")
            
        logger.info(f"Successfully scraped tweets for {len(twitter.cache)} users")

        # Continue with the rest of your analysis...
        logger.info("Starting analysis generation...")
        generator = ReportGenerator(
            api_key=config['openai_api_key'],
            model=config['model_name'],
            max_tokens=config['max_tokens'],
            temperature=config['temperature']
        )
        generator.cache['rankings'] = top_20
        generator.cache['tweets'] = twitter.cache

        report_file = await generator.generate_full_report()
        logger.info(f"Analysis report generated: {report_file}")

        # Read the generated report content
        with open(report_file, 'r', encoding='utf-8') as file:
            report_content = file.read()

        # Initialize TelegramSender
        bot_token = config['bot_api_key']
        channel_id = config['channel_id']
        sender = TelegramSender(bot_token)

        # Format and send the report sections
        top_yappers_message = await sender.format_top_yappers(report_content)
        await sender.send_message(channel_id, top_yappers_message)

        whats_yappening_messages = await sender.format_whats_yappening(report_content)
        for message in whats_yappening_messages:
            await sender.send_message(channel_id, message)

        # Clear caches
        kaito.cache.clear()
        twitter.cache.clear()
        generator.cache.clear()

        logger.info("Complete analysis pipeline finished successfully!")

    except Exception as e:
        logger.error(f"Error in analysis pipeline: {str(e)}", exc_info=True)
        # Optionally, send error notification to Telegram
        try:
            bot_token = config['bot_api_key']
            channel_id = config['channel_id']
            sender = TelegramSender(bot_token)
            error_message = f"❌ Analysis pipeline error: {str(e)}"
            await sender.send_message(channel_id, error_message)
        except:
            logger.error("Failed to send error notification")

def get_next_run_time(scheduler: AsyncIOScheduler, run_time: str, tz: pytz.timezone) -> datetime:
    """Calculate the next run time for the scheduler"""
    now = datetime.now(tz)
    run_hour, run_minute = map(int, run_time.split(':'))
    next_run = now.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
    
    if next_run <= now:
        next_run += timedelta(days=1)
    
    return next_run

async def scheduled_task():
    """Function to be used when switching to scheduled mode"""
    while True:
        await run_analysis(load_environment())
        # Wait for 1 hour before next run
        await asyncio.sleep(3600)

async def main():
    if SCHEDULED_MODE:
        logger.info("Starting in scheduled mode...")
        await scheduled_task()
    else:
        logger.info("Starting in single-run mode...")
        await run_analysis(load_environment())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)  
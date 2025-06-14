#!/usr/bin/env python3
"""
Raplink Service - VPN Link Scraper and Tester
"""

import argparse
import asyncio
import logging
from typing import List, Dict
from datetime import datetime

import scrapper
import extractor
import duplicate
import manager

from utils import read_channels_from_file

__version__ = "1.0.0"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('raplink.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ChannelScraper:
    """Scrape multiple Telegram channels for VPN links"""
    
    def __init__(self, channels: List[str]):
        self.channels = channels
        self.extractor = extractor.VPNLinkExtractor()
        self.duplicate_checker = duplicate.DuplicateChecker()
        
    async def scrape_channel(self, channel: str) -> Dict[str, List[str]]:
        """Scrape a single channel"""
        try:
            logger.info(f"Scraping channel: {channel}")
            scraper = scrapper.TelegramChannelScraper(channel)
            items = scraper.get_items()
            
            all_links = {'vmess': [], 'vless': [], 'ss': [], 'trojan': [], 'ssr': []}
            
            for post in items:
                if hasattr(post, 'content') and post.content:
                    links = self.extractor.extract_links(post.content)
                    for protocol in all_links:
                        all_links[protocol].extend(links[protocol])
            
            # Remove duplicates within this channel
            channel_dedup = duplicate.DuplicateChecker()
            all_links = channel_dedup.deduplicate_links(all_links)
            
            logger.info(f"Channel {channel}: Found {sum(len(v) for v in all_links.values())} valid links")
            return all_links
            
        except Exception as e:
            logger.error(f"Error scraping channel {channel}: {e}")
            return {'vmess': [], 'vless': [], 'ss': [], 'trojan': [], 'ssr': []}
    
    async def scrape_all_channels(self) -> Dict[str, List[str]]:
        """Scrape all channels concurrently"""
        tasks = [self.scrape_channel(channel) for channel in self.channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        combined_links = {'vmess': [], 'vless': [], 'ss': [], 'trojan': [], 'ssr': []}
        
        for result in results:
            if isinstance(result, dict):
                for protocol in combined_links:
                    combined_links[protocol].extend(result[protocol])
        
        # Final global deduplication across all channels
        combined_links = self.duplicate_checker.deduplicate_links(combined_links)
        
        return combined_links


async def main():
    parser = argparse.ArgumentParser(description='RapLink Service - VPN Link Scraper and Tester')
    parser.add_argument('--input', required=True,
                      help='List of Telegram channels to scrape')
    parser.add_argument('--output', default='vpn_links.json',
                      help='Output file for scraped links')
    parser.add_argument('--rayping-url', default='http://localhost:8080',
                      help='URL of the rayping service')
    parser.add_argument('--test-timeout', type=int, default=10,
                      help='Timeout for link testing in seconds')
    parser.add_argument('--export-only', action='store_true',
                      help='Only export links without testing')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    
    channels = read_channels_from_file(args.input)
    
    logger.info(f"Raplink Service {__version__} starting...")
    logger.info(f"Channels to scrape: {channels}")
    
    # Initialize components
    scraper = ChannelScraper(channels)
    link_manager = manager.LinkManager(args.output)
    
    try:
        logger.info("Starting channel scrape...")
        links = await scraper.scrape_all_channels()
        
        total_links = sum(len(v) for v in links.values())
        logger.info(f"Total valid links found: {total_links}")
        
        if total_links == 0:
            logger.warning("No valid links found. Check your channels and try again.")
            return
        
        logger.info("Saving validated links...")
        metadata = {
            'channels': channels,
            'scraping_timestamp': datetime.now().isoformat(),
            'version': __version__,
            'validation_enabled': True
        }
        link_manager.save_links(links, metadata)
        
        logger.info("Exporting links for testing...")
        link_manager.export_for_testing(links)
        
        logger.info("Scraping completed successfully!")
        
    except Exception as e:
        logger.error(f"Main process error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())

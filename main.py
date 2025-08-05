#!/usr/bin/env python3
"""
Enhanced Instagram DM Bot with Session Persistence
Automatically processes Instagram DMs and posts content to Buffer
"""

import os
import sys
import json
import pickle
import time
import random
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import re

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# Environment variables
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('instagram_bot.log')
    ]
)
logger = logging.getLogger(__name__)

class InstagramDMBot:
    """Base Instagram DM Bot class"""
    
    def __init__(self, username: str, password: str, buffer_token: str, buffer_profile_id: str):
        self.username = username
        self.password = password
        self.buffer_token = buffer_token
        self.buffer_profile_id = buffer_profile_id
        self.driver = None
        self.processed_messages: Set[str] = set()
        
        # Rate limiting
        self.last_action_time = 0
        self.min_delay = 2
        self.max_delay = 5
        
    def human_delay(self, min_seconds=2, max_seconds=5):
        """Add human-like delays"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
        self.last_action_time = time.time()
        
    def test_buffer_connection(self) -> bool:
        """Test Buffer API connection"""
        try:
            headers = {'Authorization': f'Bearer {self.buffer_token}'}
            response = requests.get('https://api.bufferapp.com/1/user.json', headers=headers)
            
            if response.status_code == 200:
                logger.info("✅ Buffer API connection successful")
                return True
            else:
                logger.error(f"❌ Buffer API connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Buffer API test failed: {str(e)}")
            return False
    
    def login_instagram(self) -> bool:
        """Login to Instagram"""
        try:
            logger.info("🔐 Logging into Instagram...")
            self.driver.get("https://www.instagram.com/accounts/login/")
            self.human_delay(3, 5)
            
            # Accept cookies if present
            try:
                accept_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'Allow')]"))
                )
                accept_btn.click()
                self.human_delay(2, 3)
            except TimeoutException:
                pass
            
            # Enter username
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            username_input.clear()
            for char in self.username:
                username_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            self.human_delay(1, 2)
            
            # Enter password
            password_input = self.driver.find_element(By.NAME, "password")
            password_input.clear()
            for char in self.password:
                password_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            self.human_delay(1, 2)
            
            # Click login
            login_btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            login_btn.click()
            
            # Wait for login to complete
            self.human_delay(5, 8)
            
            # Handle potential 2FA or security checks
            self.handle_login_challenges()
            
            # Verify login success
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/direct/')]"))
                )
                logger.info("✅ Instagram login successful")
                return True
            except TimeoutException:
                logger.error("❌ Login verification failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Instagram login failed: {str(e)}")
            return False
    
    def handle_login_challenges(self):
        """Handle 2FA and security challenges"""
        try:
            # Check for "Save Your Login Info" prompt
            try:
                not_now_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
                )
                not_now_btn.click()
                self.human_delay(2, 3)
            except TimeoutException:
                pass
            
            # Check for notification prompt
            try:
                not_now_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now') or contains(text(), 'Cancel')]"))
                )
                not_now_btn.click()
                self.human_delay(2, 3)
            except TimeoutException:
                pass
                
        except Exception as e:
            logger.warning(f"⚠️ Challenge handling warning: {str(e)}")
    
    def navigate_to_dms(self) -> bool:
        """Navigate to Instagram Direct Messages"""
        try:
            logger.info("📨 Navigating to DMs...")
            
            # Click on Direct Messages
            dm_link = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/direct/')]"))
            )
            dm_link.click()
            
            self.human_delay(3, 5)
            
            # Verify we're in DMs
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'message') or contains(text(), 'Direct')]"))
                )
                logger.info("✅ Successfully navigated to DMs")
                return True
            except TimeoutException:
                logger.error("❌ Failed to verify DM navigation")
                return False
                
        except Exception as e:
            logger.error(f"❌ DM navigation failed: {str(e)}")
            return False
    
    def get_new_messages(self) -> List[Dict]:
        """Extract new messages from DMs"""
        messages = []
        try:
            logger.info("🔍 Scanning for new messages...")
            
            # Find all conversation threads
            conversations = self.driver.find_elements(By.XPATH, "//div[contains(@role, 'button') and contains(@class, 'conversation')]")
            
            for i, conversation in enumerate(conversations[:5]):  # Limit to first 5 conversations
                try:
                    conversation.click()
                    self.human_delay(2, 3)
                    
                    # Get conversation messages
                    message_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'message') and contains(@data-testid, 'message')]")
                    
                    for msg_elem in message_elements[-3:]:  # Check last 3 messages
                        try:
                            # Extract message content
                            message_text = msg_elem.text.strip()
                            
                            # Look for Instagram URLs
                            if 'instagram.com' in message_text or 'reel' in message_text.lower():
                                message_id = f"{i}_{hash(message_text)}"
                                
                                if message_id not in self.processed_messages:
                                    messages.append({
                                        'id': message_id,
                                        'content': message_text,
                                        'url': self.extract_instagram_url(message_text)
                                    })
                                    
                        except Exception as e:
                            logger.warning(f"⚠️ Error processing message: {str(e)}")
                            continue
                    
                    self.human_delay(1, 2)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Error processing conversation {i}: {str(e)}")
                    continue
            
            logger.info(f"📥 Found {len(messages)} new messages")
            return messages
            
        except Exception as e:
            logger.error(f"❌ Failed to get messages: {str(e)}")
            return []
    
    def extract_instagram_url(self, text: str) -> Optional[str]:
        """Extract Instagram URL from message text"""
        url_pattern = r'https?://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?'
        match = re.search(url_pattern, text)
        return match.group(0) if match else None
    
    def add_to_buffer_fixed(self, message: Dict) -> bool:
        """Add content to Buffer with fixed implementation"""
        try:
            url = message.get('url')
            if not url:
                logger.warning("⚠️ No Instagram URL found in message")
                return False
            
            # Prepare Buffer post data
            post_data = {
                'text': f"Check out this amazing content! {url}",
                'profile_ids[]': self.buffer_profile_id,
                'shorten': 'true'
            }
            
            headers = {
                'Authorization': f'Bearer {self.buffer_token}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            # Create Buffer post
            response = requests.post(
                'https://api.bufferapp.com/1/updates/create.json',
                data=post_data,
                headers=headers
            )
            
            if response.status_code == 200:
                self.processed_messages.add(message['id'])
                logger.info(f"✅ Successfully added to Buffer: {url}")
                return True
            else:
                logger.error(f"❌ Buffer API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to add to Buffer: {str(e)}")
            return False

class PersistentInstagramDMBot(InstagramDMBot):
    """Enhanced Instagram DM Bot with Session Persistence"""
    
    def __init__(self, username, password, buffer_token, buffer_profile_id):
        super().__init__(username, password, buffer_token, buffer_profile_id)
        self.session_file = f"instagram_session_{username}.pkl"
        self.cookies_file = f"instagram_cookies_{username}.json"
        
    def setup_driver(self, headless=True, use_proxy=False, proxy_address=None):
        """Setup Chrome driver with session persistence"""
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument("--headless")
        
        # Enhanced anti-detection measures
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        
        # IMPORTANT: Use persistent user data directory
        user_data_dir = f"/tmp/chrome_profile_{self.username}"
        os.makedirs(user_data_dir, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
        chrome_options.add_argument(f"--profile-directory=Default")
        
        # Disable automation indicators
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Randomized viewport sizes
        viewports = ["1366,768", "1920,1080", "1440,900", "1536,864"]
        chrome_options.add_argument(f"--window-size={random.choice(viewports)}")
        
        # Stable user agent
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        if use_proxy and proxy_address:
            chrome_options.add_argument(f"--proxy-server={proxy_address}")
        
        # Additional preferences for persistence
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "geolocation": 2,
                "media_stream": 2,
            },
            "profile.password_manager_enabled": True,
            "credentials_enable_service": True,
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Use webdriver manager for automatic chromedriver management
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Execute stealth scripts
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
        self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
        
    def save_session(self):
        """Save current session data"""
        try:
            # Save cookies
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f)
            
            # Save session info
            session_data = {
                'last_login': datetime.now().isoformat(),
                'user_agent': self.driver.execute_script("return navigator.userAgent"),
                'current_url': self.driver.current_url,
                'processed_messages': list(self.processed_messages)
            }
            
            with open(self.session_file, 'wb') as f:
                pickle.dump(session_data, f)
                
            logger.info("💾 Session saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save session: {str(e)}")
            return False
    
    def load_session(self):
        """Load existing session data"""
        try:
            # Load session info
            if os.path.exists(self.session_file):
                with open(self.session_file, 'rb') as f:
                    session_data = pickle.load(f)
                    
                self.processed_messages = set(session_data.get('processed_messages', []))
                logger.info(f"📁 Loaded {len(self.processed_messages)} processed messages from cache")
            
            # Load cookies if available
            if os.path.exists(self.cookies_file):
                # First go to Instagram
                self.driver.get("https://www.instagram.com")
                self.human_delay(2, 3)
                
                # Load cookies
                with open(self.cookies_file, 'r') as f:
                    cookies = json.load(f)
                    
                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except Exception as e:
                        # Some cookies might be invalid, skip them
                        continue
                
                # Refresh to apply cookies
                self.driver.refresh()
                self.human_delay(3, 5)
                
                logger.info("🍪 Cookies loaded successfully")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to load session: {str(e)}")
            return False
    
    def is_logged_in(self):
        """Check if user is already logged in"""
        try:
            self.driver.get("https://www.instagram.com")
            self.human_delay(3, 5)
            
            # Check for logged-in indicators
            logged_in_indicators = [
                "//a[contains(@href, '/direct/')]",
                "//svg[@aria-label='Direct']",
                "//a[contains(@href, 'accounts/edit')]",
                "//button[contains(@class, 'follow')]",
                "//div[contains(@class, 'logged-in')]"
            ]
            
            for indicator in logged_in_indicators:
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, indicator))
                    )
                    if element:
                        logger.info("✅ Already logged in!")
                        return True
                except TimeoutException:
                    continue
            
            # Check if we're on login page
            login_indicators = [
                "//input[@name='username']",
                "//input[@name='password']",
                "//button[@type='submit']"
            ]
            
            for indicator in login_indicators:
                try:
                    element = self.driver.find_element(By.XPATH, indicator)
                    if element:
                        logger.info("🔐 Not logged in, need to authenticate")
                        return False
                except:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking login status: {str(e)}")
            return False
    
    def smart_login(self):
        """Smart login that only logs in when necessary"""
        try:
            # Setup driver first
            self.setup_driver(headless=True)
            
            # Try to load existing session
            session_loaded = self.load_session()
            
            # Check if already logged in
            if self.is_logged_in():
                logger.info("🎉 Using existing session - no login required!")
                return True
            
            # If not logged in, perform login
            logger.info("🔑 Session expired or not found, logging in...")
            if self.login_instagram():
                # Save session after successful login
                self.save_session()
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"❌ Smart login failed: {str(e)}")
            return False
    
    def run_scheduled_check(self):
        """Run the daily check with session persistence"""
        try:
            logger.info("🕐 Running scheduled DM check...")
            
            # Use smart login instead of always logging in
            if not self.smart_login():
                logger.error("❌ Authentication failed")
                return False
            
            # Navigate to DMs
            if not self.navigate_to_dms():
                logger.error("❌ Failed to navigate to DMs")
                return False
            
            # Process messages
            new_messages = self.get_new_messages()
            processed_count = 0
            
            for message in new_messages:
                if self.add_to_buffer_fixed(message):
                    processed_count += 1
                self.human_delay(3, 6)
            
            # Save session after successful run
            self.save_session()
            
            logger.info(f"✅ Check complete! Processed {processed_count} messages")
            return True
            
        except Exception as e:
            logger.error(f"❌ Scheduled check failed: {str(e)}")
            return False
        finally:
            # Close browser to free resources
            if self.driver:
                self.driver.quit()

def setup_environment_variables():
    """Load environment variables"""
    load_dotenv()
    
    return {
        'username': os.getenv('INSTAGRAM_USERNAME'),
        'password': os.getenv('INSTAGRAM_PASSWORD'),
        'buffer_token': os.getenv('BUFFER_ACCESS_TOKEN'),
        'buffer_profile_id': os.getenv('BUFFER_PROFILE_ID')
    }

def create_setup_files():
    """Create setup files for hosting"""
    logger.info("📄 Creating setup files...")
    
    # These files are already created by the artifact system
    # Just log that they should be created
    files_to_create = [
        'requirements.txt',
        '.github/workflows/instagram-bot.yml',
        '.env.example'
    ]
    
    for file_name in files_to_create:
        if os.path.exists(file_name):
            logger.info(f"✅ {file_name} already exists")
        else:
            logger.warning(f"⚠️ {file_name} needs to be created")

if __name__ == "__main__":
    logger.info("🚀 Starting Instagram DM Bot...")
    
    # Create setup files
    create_setup_files()
    
    # Load configuration from environment
    config = setup_environment_variables()
    
    # Validate configuration
    missing_vars = [key for key, value in config.items() if not value]
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        logger.error("Please check your .env file or GitHub secrets.")
        sys.exit(1)
    
    # Create bot with persistent sessions
    bot = PersistentInstagramDMBot(
        username=config['username'],
        password=config['password'],
        buffer_token=config['buffer_token'],
        buffer_profile_id=config['buffer_profile_id']
    )
    
    # Test Buffer connection
    if not bot.test_buffer_connection():
        logger.error("❌ Buffer connection failed")
        sys.exit(1)
    
    # Run scheduled check
    success = bot.run_scheduled_check()
    
    if success:
        logger.info("🏁 Scheduled check completed successfully!")
        sys.exit(0)
    else:
        logger.error("❌ Scheduled check failed!")
        sys.exit(1)
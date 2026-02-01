import asyncio
import re
import os
import time
import sqlite3
import random
import string
import json
import hashlib
from typing import Dict, Optional, List, Set, Tuple
from enum import Enum
from dataclasses import dataclass, field
import atexit
from datetime import datetime
import logging
import traceback

# Pyrogram imports for bot
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatType
from pyrogram.errors import (
    SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired,
    PhoneNumberInvalid, PasswordHashInvalid, FloodWait,
    UserDeactivated, ChatWriteForbidden, ChannelPrivate,
    Flood, BadRequest, Forbidden, Unauthorized
)
from pyrogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
    InlineKeyboardButton, Message
)

# Bot credentials
BOT_TOKEN = "8423319367:AAFgjxrw5h4ocfyyM12rpDylsb9kXxtHa34"
BOT_API_ID = 35530265
BOT_API_HASH = "35274a053f799bc8fe53bdde2b102e67"

# Setup logging - Clean terminal output
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)
logging.getLogger('pyrogram').setLevel(logging.ERROR)

# State management
class UserState(Enum):
    MAIN_MENU = "main_menu"
    ENTERING_API_ID = "entering_api_id"
    ENTERING_API_HASH = "entering_api_hash"
    ENTERING_PHONE = "entering_phone"
    CONFIRM_PHONE = "confirm_phone"
    ENTERING_OTP = "entering_otp"
    ENTERING_2FA = "entering_2fa"
    CONFIRM_ADD_MORE = "confirm_add_more"
    ADS_MODE_SELECT = "ads_mode_select"
    ADS_SINGLE_SELECT_ACCOUNT = "ads_single_select_account"
    ADS_MULTI_SELECT_ACCOUNTS = "ads_multi_select_accounts"
    ADS_CONFIRM_ACCOUNT = "ads_confirm_account"
    ADS_CONFIRM_MULTI_ACCOUNTS = "ads_confirm_multi_accounts"
    ADS_SET_MESSAGE_DELAY = "ads_set_message_delay"
    ADS_SET_SET_DELAY = "ads_set_set_delay"
    ADS_WAITING_MESSAGE = "ads_waiting_message"
    ADS_SENDING = "ads_sending"
    MANAGE_ACCOUNTS = "manage_accounts"
    SELECT_ACCOUNT_REMOVE = "select_account_remove"
    REMOVE_CONFIRM = "remove_confirm"
    ADD_ACCOUNT_ASK = "add_account_ask"

@dataclass
class UserSessionData:
    state: UserState = UserState.MAIN_MENU
    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    phone: Optional[str] = None
    phone_code_hash: Optional[str] = None
    client: Optional[Client] = None
    timestamp: Optional[float] = None
    selected_account: Optional[str] = None
    selected_accounts: Set[str] = field(default_factory=set)
    temp_2fa_hint: Optional[str] = None
    ads_delay: Optional[int] = None
    ads_set_delay: Optional[int] = None
    ads_message: Optional[str] = None
    stop_requested: bool = False
    sending_task: Optional[asyncio.Task] = None
    ads_message_id: Optional[int] = None
    is_multi_account: bool = False
    status_message_id: Optional[int] = None
    last_message_id: Optional[int] = None

class ChatSafety:
    """Enhanced safety and behavior tracking"""
    
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.last_send_time = 0
        self.slow_mode_delay = 0
        self.send_count = 0
        self.flood_wait_count = 0
        self.last_message_hash = None
        self.consecutive_errors = 0
        self.last_error_time = 0
        self.send_weight = 1.0
        self.deletion_count = 0
        
    def can_send_now(self) -> Tuple[bool, float]:
        """Check if we can send now with adaptive timing"""
        if self.last_send_time == 0:
            return True, 0
            
        elapsed = time.time() - self.last_send_time
        
        # Apply adaptive slowing for errors and deletions
        error_slowdown = 1.0 + (self.consecutive_errors * 0.5) + (self.deletion_count * 0.3)
        required_delay = max(self.slow_mode_delay, 3) * error_slowdown * self.send_weight
        
        if elapsed >= required_delay:
            return True, 0
        else:
            return False, required_delay - elapsed
    
    def record_send(self, message_hash: str = None):
        """Record successful send"""
        self.last_send_time = time.time()
        self.send_count += 1
        self.consecutive_errors = 0
        if message_hash:
            self.last_message_hash = message_hash
    
    def record_error(self):
        """Record error and adjust behavior"""
        self.consecutive_errors += 1
        self.last_error_time = time.time()
        
        if self.consecutive_errors >= 3:
            self.send_weight = max(0.3, self.send_weight * 0.7)
    
    def record_deletion(self):
        """Record message deletion"""
        self.deletion_count += 1
        self.send_weight = max(0.2, self.send_weight * 0.5)
    
    def is_duplicate_content(self, content: str) -> bool:
        """Check for duplicate content"""
        if not self.last_message_hash or not content:
            return False
        current_hash = hashlib.md5(content.encode()).hexdigest()
        return current_hash == self.last_message_hash

class EliteBehaviorEngine:
    """Elite human-like behavior with anti-detection"""
    
    def __init__(self):
        self.global_slowdown = 1.0
        self.burst_counter = 0
        self.total_sends = 0
        self.fatigue_level = 0
        
    def calculate_delay(self, text_length: int) -> float:
        """Calculate human-like delay"""
        # Base typing delay
        base_delay = max(0.8, text_length * 0.003)
        base_delay = min(base_delay, 4.0)
        
        # Random variation
        variation = random.uniform(0.6, 1.4)
        
        # Thinking pauses (25% chance)
        if random.random() > 0.75:
            base_delay += random.uniform(0.5, 1.5)
        
        # Micro-pauses (40% chance)
        if random.random() > 0.6:
            base_delay += random.uniform(0.1, 0.4)
        
        return base_delay * variation * self.global_slowdown
    
    def update_fatigue(self, sends: int):
        """Update fatigue level"""
        self.total_sends += sends
        self.fatigue_level = min(100, self.fatigue_level + (sends * 1.5))
    
    def increase_global_slowdown(self):
        """Increase global slowdown after errors"""
        self.global_slowdown = min(4.0, self.global_slowdown * 1.4)
    
    def modify_content(self, content: str) -> str:
        """Apply invisible modifications to prevent duplicate filtering"""
        if not content or len(content) < 5:
            return content
        
        # Different modification strategies
        strategies = [
            lambda c: self._add_invisible_chars(c),
            lambda c: self._swap_characters(c),
            lambda c: self._change_punctuation(c),
        ]
        
        modified = content
        for _ in range(2):
            modified = random.choice(strategies)(modified)
        
        return modified
    
    def _add_invisible_chars(self, content: str) -> str:
        invisible_chars = ['\u200b', '\u200c', '\u200d', '\u2060']
        
        if len(content) < 10:
            return content
        
        for _ in range(2):
            pos = random.randint(1, len(content) - 2)
            char = random.choice(invisible_chars)
            content = content[:pos] + char + content[pos:]
        
        return content
    
    def _swap_characters(self, content: str) -> str:
        if len(content) < 15:
            return content
        
        chars = list(content)
        
        for _ in range(2):
            i = random.randint(0, len(chars) - 2)
            j = random.randint(0, len(chars) - 2)
            if i != j:
                chars[i], chars[j] = chars[j], chars[i]
        
        return ''.join(chars)
    
    def _change_punctuation(self, content: str) -> str:
        replacements = {
            '.': ['.', '…', '..'],
            ',': [',', ' ,'],
            '!': ['!', '‼', ' !!'],
            '?': ['?', '⁇', ' ??'],
        }
        
        for old, new_options in replacements.items():
            if old in content and random.random() < 0.3:
                content = content.replace(old, random.choice(new_options), 1)
        
        return content

class Database:
    def __init__(self):
        self.db_path = 'sessions.db'
        self._ensure_clean_db()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_db()
        atexit.register(self.close)
    
    def _ensure_clean_db(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except:
                pass
        
        journal_path = f"{self.db_path}-journal"
        if os.path.exists(journal_path):
            try:
                os.remove(journal_path)
            except:
                pass
    
    def init_db(self):
        try:
            self.cursor.execute("DROP TABLE IF EXISTS accounts")
            self.cursor.execute("DROP TABLE IF EXISTS groups")
            self.conn.commit()
            
            self.cursor.execute('''
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    phone TEXT NOT NULL,
                    username TEXT,
                    string_session TEXT NOT NULL,
                    api_id TEXT NOT NULL,
                    api_hash TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, account_id)
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    group_username TEXT,
                    group_title TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(account_id, group_id)
                )
            ''')
            
            self.cursor.execute('CREATE INDEX idx_accounts_user_id ON accounts(user_id)')
            self.cursor.execute('CREATE INDEX idx_accounts_account_id ON accounts(account_id)')
            self.cursor.execute('CREATE INDEX idx_groups_account_id ON groups(account_id)')
            
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def add_account(self, user_id: int, account_id: int, phone: str, username: str, string_session: str, api_id: str, api_hash: str):
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO accounts (user_id, account_id, phone, username, string_session, api_id, api_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, account_id, phone, username, string_session, api_id, api_hash))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Database error adding account: {e}")
            return False
    
    def delete_account(self, user_id: int, username: str):
        try:
            self.cursor.execute('''
                DELETE FROM accounts 
                WHERE user_id = ? AND username = ?
            ''', (user_id, username))
            self.conn.commit()
            deleted = self.cursor.rowcount > 0
            return deleted
        except Exception as e:
            logger.error(f"Database error deleting account: {e}")
            return False
    
    def get_user_accounts(self, user_id: int) -> List[tuple]:
        try:
            self.cursor.execute('''
                SELECT account_id, username, string_session, api_id, api_hash FROM accounts 
                WHERE user_id = ? ORDER BY added_at DESC
            ''', (user_id,))
            return self.cursor.fetchall()
        except Exception as e:
            logger.error(f"Database error getting user accounts: {e}")
            return []
    
    def get_account_by_username(self, user_id: int, username: str):
        try:
            self.cursor.execute('''
                SELECT account_id, string_session, api_id, api_hash FROM accounts 
                WHERE user_id = ? AND username = ?
            ''', (user_id, username))
            return self.cursor.fetchone()
        except Exception as e:
            logger.error(f"Database error getting account by username: {e}")
            return None
    
    def update_groups(self, account_id: int, groups: List[tuple]):
        try:
            self.cursor.execute('DELETE FROM groups WHERE account_id = ?', (account_id,))
            for group_id, group_username, group_title in groups:
                self.cursor.execute('''
                    INSERT OR REPLACE INTO groups (account_id, group_id, group_username, group_title)
                    VALUES (?, ?, ?, ?)
                ''', (account_id, group_id, group_username, group_title))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Database error updating groups: {e}")
    
    def get_groups(self, account_id: int) -> List[tuple]:
        try:
            self.cursor.execute('''
                SELECT group_id, group_username, group_title FROM groups 
                WHERE account_id = ? ORDER BY group_title
            ''', (account_id,))
            return self.cursor.fetchall()
        except Exception as e:
            logger.error(f"Database error getting groups: {e}")
            return []
    
    def close(self):
        try:
            self.conn.close()
        except:
            pass

class TelegramBot:
    def __init__(self):
        self.user_sessions: Dict[int, UserSessionData] = {}
        self.bot_client = None
        self.bot_username = ""
        self.db = Database()
        self.active_tasks: Set[asyncio.Task] = set()
        self.status_messages: Dict[int, Message] = {}
        
    async def start(self):
        """Initialize and start the bot"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
        self.bot_client = Client(
            "bot_session",
            api_id=BOT_API_ID,
            api_hash=BOT_API_HASH,
            bot_token=BOT_TOKEN,
            workers=200,
            in_memory=True
        )
        
        @self.bot_client.on_message(filters.command("start") & filters.private)
        async def start_handler(client, message):
            await self.handle_start(message)
        
        @self.bot_client.on_message(filters.private & filters.text)
        async def message_handler(client, message):
            await self.handle_message(message)
        
        @self.bot_client.on_message(filters.private & ~filters.text)
        async def media_handler(client, message):
            await self.handle_media(message)
        
        try:
            await self.bot_client.start()
            me = await self.bot_client.get_me()
            self.bot_username = me.username
            
            print(f"✅ @{self.bot_username} STARTED")
            
            asyncio.create_task(self.cleanup_stale_sessions())
            
            await idle()
            
        except Exception as e:
            logger.error(f"Fatal error starting bot: {e}")
            raise
        finally:
            if self.bot_client:
                await self.bot_client.stop()
    
    async def cleanup_stale_sessions(self):
        while True:
            await asyncio.sleep(300)
            current_time = time.time()
            stale_users = []
            
            for user_id, session in list(self.user_sessions.items()):
                if session.timestamp and (current_time - session.timestamp > 3600):
                    stale_users.append(user_id)
            
            for user_id in stale_users:
                del self.user_sessions[user_id]
    
    def get_user_session(self, user_id: int) -> UserSessionData:
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = UserSessionData()
        session = self.user_sessions[user_id]
        session.timestamp = time.time()
        return session
    
    async def cleanup_client(self, user_id: int):
        session = self.get_user_session(user_id)
        
        if session.client:
            try:
                if await session.client.is_connected():
                    await session.client.disconnect()
            except:
                pass
            session.client = None
        
        session.phone_code_hash = None
    
    def reset_user_session(self, user_id: int):
        if user_id in self.user_sessions:
            asyncio.create_task(self.cleanup_client(user_id))
            self.user_sessions[user_id] = UserSessionData()
    
    def get_main_menu_buttons(self) -> ReplyKeyboardMarkup:
        rows = []
        rows.append([KeyboardButton(text="🚀 START ADS")])
        rows.append([
            KeyboardButton(text="➕ ADD ACCOUNT"),
            KeyboardButton(text="👥 MANAGE ACCOUNT")
        ])
        rows.append([KeyboardButton(text="❓ HELP")])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    
    def get_back_button(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 BACK")]],
            resize_keyboard=True
        )
    
    def get_yes_no_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[[
                KeyboardButton(text="✅ YES"),
                KeyboardButton(text="❌ NO")
            ]],
            resize_keyboard=True
        )
    
    def get_stop_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🛑 STOP SENDING")]],
            resize_keyboard=True
        )
    
    async def handle_start(self, message: Message):
        try:
            user_id = message.from_user.id
            session = self.get_user_session(user_id)
            session.state = UserState.MAIN_MENU
            
            await self.send_or_update_message(user_id, message,
                "🤖 WELCOME TO ADBOT\nPLEASE CHOOSE OPTION BELOW :",
                self.get_main_menu_buttons())
            
        except Exception as e:
            logger.error(f"Error in handle_start: {e}")
            session = self.get_user_session(message.from_user.id)
            msg = await message.reply("🤖 WELCOME TO ADBOT\nPLEASE CHOOSE OPTION BELOW :", 
                                    reply_markup=self.get_main_menu_buttons())
            session.last_message_id = msg.id
    
    async def handle_message(self, message: Message):
        try:
            if not message.from_user:
                return
            
            user_id = message.from_user.id
            message_text = message.text.strip() if message.text else ""
            session = self.get_user_session(user_id)
            session.timestamp = time.time()
            
            if message_text == "🔙 BACK":
                await self.show_main_menu(user_id, message)
                return
            
            if message_text == "🛑 STOP SENDING":
                await self.handle_stop_button(user_id, message)
                return
            
            state_handlers = {
                UserState.MAIN_MENU: self.handle_main_menu,
                UserState.ENTERING_API_ID: self.handle_api_id,
                UserState.ENTERING_API_HASH: self.handle_api_hash,
                UserState.ENTERING_PHONE: self.handle_phone,
                UserState.CONFIRM_PHONE: self.handle_confirm_phone,
                UserState.ENTERING_OTP: self.handle_otp,
                UserState.ENTERING_2FA: self.handle_2fa,
                UserState.CONFIRM_ADD_MORE: self.handle_confirm_add_more,
                UserState.ADS_MODE_SELECT: self.handle_ads_mode_select,
                UserState.ADS_SINGLE_SELECT_ACCOUNT: self.handle_ads_single_select_account,
                UserState.ADS_MULTI_SELECT_ACCOUNTS: self.handle_ads_multi_select_accounts,
                UserState.ADS_CONFIRM_ACCOUNT: self.handle_ads_confirm_account,
                UserState.ADS_CONFIRM_MULTI_ACCOUNTS: self.handle_ads_confirm_multi_accounts,
                UserState.ADS_SET_MESSAGE_DELAY: self.handle_ads_set_message_delay,
                UserState.ADS_SET_SET_DELAY: self.handle_ads_set_set_delay,
                UserState.ADS_WAITING_MESSAGE: self.handle_ads_waiting_message,
                UserState.ADS_SENDING: self.handle_ads_sending,
                UserState.MANAGE_ACCOUNTS: self.handle_manage_accounts,
                UserState.SELECT_ACCOUNT_REMOVE: self.handle_select_account_remove,
                UserState.REMOVE_CONFIRM: self.handle_remove_confirm,
                UserState.ADD_ACCOUNT_ASK: self.handle_add_account_ask,
            }
            
            if session.state in state_handlers:
                await state_handlers[session.state](user_id, message, message_text)
            else:
                await self.show_main_menu(user_id, message)
        
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            await self.show_main_menu(user_id, message)
    
    async def handle_media(self, message: Message):
        user_id = message.from_user.id
        session = self.get_user_session(user_id)
        
        if session.state == UserState.ADS_WAITING_MESSAGE:
            session.ads_message_id = message.id
            await self.start_sending_ads(user_id, message)
    
    async def show_main_menu(self, user_id: int, message: Message):
        session = self.get_user_session(user_id)
        session.state = UserState.MAIN_MENU
        
        await self.send_or_update_message(user_id, message,
            "🤖 WELCOME TO ADBOT\nPLEASE CHOOSE OPTION BELOW :",
            self.get_main_menu_buttons())
    
    async def handle_stop_button(self, user_id: int, message: Message):
        session = self.get_user_session(user_id)
        session.stop_requested = True
        
        if session.sending_task and not session.sending_task.done():
            session.sending_task.cancel()
            try:
                await session.sending_task
            except asyncio.CancelledError:
                pass
        
        if user_id in self.status_messages:
            try:
                await self.status_messages[user_id].delete()
            except:
                pass
            del self.status_messages[user_id]
        
        session.stop_requested = False
        await self.show_main_menu(user_id, message)
    
    async def handle_main_menu(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "🚀 START ADS":
            session.state = UserState.ADS_MODE_SELECT
            await self.send_or_update_message(user_id, message,
                "📱 SELECT ADVERTISING MODE",
                self.get_ads_mode_buttons())
        
        elif message_text == "➕ ADD ACCOUNT":
            await self.start_add_account(user_id, message)  # OLD METHOD WAPAS
        
        elif message_text == "👥 MANAGE ACCOUNT":
            await self.show_manage_accounts(user_id, message)
        
        elif message_text == "❓ HELP":
            await self.send_or_update_message(user_id, message,
                "📞 Contact: @seIlyourmom\nFor issues & queries",
                self.get_main_menu_buttons())
    
    def get_ads_mode_buttons(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="👤 SINGLE ACCOUNT")],
                [KeyboardButton(text="👥 SELECTED ACCOUNTS")],
                [KeyboardButton(text="🌟 ALL ACCOUNTS")],
                [KeyboardButton(text="🔙 BACK")]
            ],
            resize_keyboard=True
        )
    
    async def handle_ads_mode_select(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "👤 SINGLE ACCOUNT":
            user_accounts = self.db.get_user_accounts(user_id)
            if not user_accounts:
                session.state = UserState.ADD_ACCOUNT_ASK
                await self.send_or_update_message(user_id, message,
                    "❌ NO ACCOUNTS FOUND\n\nDO YOU WANT TO ADD ACCOUNT?",
                    self.get_yes_no_keyboard())
            else:
                session.state = UserState.ADS_SINGLE_SELECT_ACCOUNT
                await self.show_account_selection(user_id, message)
        
        elif message_text == "👥 SELECTED ACCOUNTS":
            user_accounts = self.db.get_user_accounts(user_id)
            if not user_accounts:
                session.state = UserState.ADD_ACCOUNT_ASK
                await self.send_or_update_message(user_id, message,
                    "❌ NO ACCOUNTS FOUND\n\nDO YOU WANT TO ADD ACCOUNT?",
                    self.get_yes_no_keyboard())
            else:
                session.state = UserState.ADS_MULTI_SELECT_ACCOUNTS
                await self.show_multi_account_selection(user_id, message)
        
        elif message_text == "🌟 ALL ACCOUNTS":
            user_accounts = self.db.get_user_accounts(user_id)
            if not user_accounts:
                session.state = UserState.ADD_ACCOUNT_ASK
                await self.send_or_update_message(user_id, message,
                    "❌ NO ACCOUNTS FOUND\n\nDO YOU WANT TO ADD ACCOUNT?",
                    self.get_yes_no_keyboard())
            else:
                session.selected_accounts.clear()
                for _, username, _, _, _ in user_accounts:
                    session.selected_accounts.add(username)
                session.is_multi_account = True
                session.state = UserState.ADS_CONFIRM_MULTI_ACCOUNTS
                
                selected_list = "\n".join([f"• {acc}" for acc in session.selected_accounts])
                await self.send_or_update_message(user_id, message,
                    f"✅ SELECTED ALL ACCOUNTS\n\n{selected_list}\n\nCONTINUE?",
                    self.get_yes_no_keyboard())
        
        elif message_text == "🔙 BACK":
            await self.show_main_menu(user_id, message)
    
    async def show_account_selection(self, user_id: int, message: Message):
        session = self.get_user_session(user_id)
        user_accounts = self.db.get_user_accounts(user_id)
        accounts = [username for _, username, _, _, _ in user_accounts]
        
        rows = []
        for i in range(0, len(accounts), 2):
            row_accounts = accounts[i:i+2]
            buttons = [KeyboardButton(text=acc) for acc in row_accounts]
            rows.append(buttons)
        rows.append([KeyboardButton(text="🔙 BACK")])
        
        buttons = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
        
        await self.send_or_update_message(user_id, message,
            "👤 SELECT YOUR ACCOUNT TO PROCEED WITH :",
            buttons)
    
    async def show_multi_account_selection(self, user_id: int, message: Message):
        session = self.get_user_session(user_id)
        session.selected_accounts.clear()
        
        user_accounts = self.db.get_user_accounts(user_id)
        accounts = [username for _, username, _, _, _ in user_accounts]
        
        rows = []
        for i in range(0, len(accounts), 2):
            row_accounts = accounts[i:i+2]
            buttons = [KeyboardButton(text=acc) for acc in row_accounts]
            rows.append(buttons)
        rows.append([
            KeyboardButton(text="✅ DONE"),
            KeyboardButton(text="🔙 BACK")
        ])
        
        buttons = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
        
        await self.send_or_update_message(user_id, message,
            "👥 SELECT ACCOUNTS (Click to select/deselect):",
            buttons)
    
    async def handle_ads_single_select_account(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        user_accounts = self.db.get_user_accounts(user_id)
        accounts = [username for _, username, _, _, _ in user_accounts]
        
        if message_text in accounts:
            session.selected_account = message_text
            session.is_multi_account = False
            session.state = UserState.ADS_SET_MESSAGE_DELAY  # FIXED: Directly go to delay setting
            await self.send_or_update_message(user_id, message,
                f"✅ SELECTED {message_text}\n\n⏱️ SET DELAY BETWEEN MESSAGES (in sec) :\n\nMax: 500 sec",
                self.get_back_button())
        elif message_text == "🔙 BACK":
            session.state = UserState.ADS_MODE_SELECT
            await self.send_or_update_message(user_id, message,
                "📱 SELECT ADVERTISING MODE",
                self.get_ads_mode_buttons())
    
    async def handle_ads_multi_select_accounts(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        user_accounts = self.db.get_user_accounts(user_id)
        accounts = [username for _, username, _, _, _ in user_accounts]
        
        if message_text in accounts:
            if message_text in session.selected_accounts:
                session.selected_accounts.remove(message_text)
            else:
                session.selected_accounts.add(message_text)
            
            selected_list = "\n".join([f"• {acc}" for acc in session.selected_accounts]) if session.selected_accounts else "No accounts selected"
            await self.send_or_update_message(user_id, message,
                f"👥 SELECTED ACCOUNTS:\n\n{selected_list}\n\nClick accounts to select/deselect",
                self.get_multi_account_selection_buttons(user_accounts))
        
        elif message_text == "✅ DONE":
            if not session.selected_accounts:
                await self.send_or_update_message(user_id, message,
                    "❌ PLEASE SELECT AT LEAST 1 ACCOUNT",
                    self.get_multi_account_selection_buttons(user_accounts))
                return
            
            session.is_multi_account = True
            session.state = UserState.ADS_CONFIRM_MULTI_ACCOUNTS
            
            selected_list = "\n".join([f"• {acc}" for acc in session.selected_accounts])
            await self.send_or_update_message(user_id, message,
                f"✅ SELECTED ACCOUNTS\n\n{selected_list}\n\nCONTINUE?",
                self.get_yes_no_keyboard())
        
        elif message_text == "🔙 BACK":
            session.state = UserState.ADS_MODE_SELECT
            await self.send_or_update_message(user_id, message,
                "📱 SELECT ADVERTISING MODE",
                self.get_ads_mode_buttons())
    
    def get_multi_account_selection_buttons(self, user_accounts):
        accounts = [username for _, username, _, _, _ in user_accounts]
        
        rows = []
        for i in range(0, len(accounts), 2):
            row_accounts = accounts[i:i+2]
            buttons = [KeyboardButton(text=acc) for acc in row_accounts]
            rows.append(buttons)
        rows.append([
            KeyboardButton(text="✅ DONE"),
            KeyboardButton(text="🔙 BACK")
        ])
        
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    
    async def handle_ads_confirm_account(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "✅ YES":
            session.state = UserState.ADS_SINGLE_SELECT_ACCOUNT
            await self.show_account_selection(user_id, message)
        
        elif message_text == "❌ NO":
            session.state = UserState.ADS_SET_MESSAGE_DELAY
            await self.send_or_update_message(user_id, message,
                "⏱️ SET DELAY BETWEEN MESSAGES (in sec) :\n\nMax: 500 sec",
                self.get_back_button())
    
    async def handle_ads_confirm_multi_accounts(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "✅ YES":
            session.state = UserState.ADS_SET_MESSAGE_DELAY
            await self.send_or_update_message(user_id, message,
                "⏱️ SET DELAY BETWEEN MESSAGES (in sec) :\n\nMax: 500 sec",
                self.get_back_button())
        
        elif message_text == "❌ NO":
            session.state = UserState.ADS_MULTI_SELECT_ACCOUNTS
            await self.show_multi_account_selection(user_id, message)
    
    async def handle_ads_set_message_delay(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "🔙 BACK":
            if session.is_multi_account:
                session.state = UserState.ADS_CONFIRM_MULTI_ACCOUNTS
                selected_list = "\n".join([f"• {acc}" for acc in session.selected_accounts])
                await self.send_or_update_message(user_id, message,
                    f"✅ SELECTED ACCOUNTS\n\n{selected_list}\n\nCONTINUE?",
                    self.get_yes_no_keyboard())
            else:
                session.state = UserState.ADS_SINGLE_SELECT_ACCOUNT  # FIXED: Go back to account selection
                await self.show_account_selection(user_id, message)
            return
        
        if not message_text.isdigit():
            await self.send_or_update_message(user_id, message,
                "❌ INVALID DURATION TO SET\n\n⏱️ SET DELAY BETWEEN MESSAGES (in sec) :\nMax: 500 sec",
                self.get_back_button())
            return
        
        delay = int(message_text)
        if delay > 500:
            await self.send_or_update_message(user_id, message,
                "❌ MAX 500 sec SUPPORTED\n\n⏱️ SET DELAY BETWEEN MESSAGES (in sec) :\nMax: 500 sec",
                self.get_back_button())
            return
        
        session.ads_delay = delay
        session.state = UserState.ADS_SET_SET_DELAY
        await self.send_or_update_message(user_id, message,
            "⏳ SET DELAY BETWEEN SETS (in min) :\n\nMax: 100 min",
            self.get_back_button())
    
    async def handle_ads_set_set_delay(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "🔙 BACK":
            session.state = UserState.ADS_SET_MESSAGE_DELAY
            await self.send_or_update_message(user_id, message,
                "⏱️ SET DELAY BETWEEN MESSAGES (in sec) :\n\nMax: 500 sec",
                self.get_back_button())
            return
        
        if not message_text.isdigit():
            await self.send_or_update_message(user_id, message,
                "❌ INVALID DURATION TO SET\n\n⏳ SET DELAY BETWEEN SETS (in min) :\nMax: 100 min",
                self.get_back_button())
            return
        
        delay = int(message_text)
        if delay > 100:
            await self.send_or_update_message(user_id, message,
                "❌ MAX 100 min SUPPORTED\n\n⏳ SET DELAY BETWEEN SETS (in min) :\nMax: 100 min",
                self.get_back_button())
            return
        
        session.ads_set_delay = delay
        session.state = UserState.ADS_WAITING_MESSAGE
        await self.send_or_update_message(user_id, message,
            "📝 PREPARE YOUR ADVERTISEMENT\n\n1. Go to your Saved Messages in Telegram\n2. Come back here and press ✅ READY",
            ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ READY")],
                    [KeyboardButton(text="🔙 BACK")]
                ],
                resize_keyboard=True
            ))
    
    async def handle_ads_waiting_message(self, user_id: int, message: Message, message_text: str):
        if message_text == "✅ READY":
            await self.start_sending_ads(user_id, message)
        elif message_text == "🔙 BACK":
            session = self.get_user_session(user_id)
            session.state = UserState.ADS_SET_SET_DELAY
            await self.send_or_update_message(user_id, message,
                "⏳ SET DELAY BETWEEN SETS (in min) :\n\nMax: 100 min",
                self.get_back_button())
    
    async def handle_add_account_ask(self, user_id: int, message: Message, message_text: str):
        if message_text == "✅ YES":
            await self.start_add_account(user_id, message)  # OLD METHOD WAPAS
        elif message_text == "❌ NO":
            await self.show_main_menu(user_id, message)
    
    async def start_add_account(self, user_id: int, message: Message):
        """OLD ACCOUNT ADDING METHOD WAPAS - Jabhi aapka original kaam karta tha"""
        session = self.get_user_session(user_id)
        session.state = UserState.ENTERING_API_ID
        
        # Clear any existing session data
        session.api_id = None
        session.api_hash = None
        session.phone = None
        session.phone_code_hash = None
        
        await self.send_or_update_message(user_id, message,
            "🔑 SEND API ID :",
            self.get_back_button())
    
    async def handle_api_id(self, user_id: int, message: Message, message_text: str):
        if message_text == "🔙 BACK":
            await self.show_main_menu(user_id, message)
            return
        
        if not message_text.isdigit():
            await self.send_or_update_message(user_id, message,
                "❌ INVALID API ID\n\n🔑 SEND API ID :",
                self.get_back_button())
            return
        
        session = self.get_user_session(user_id)
        session.api_id = message_text
        session.state = UserState.ENTERING_API_HASH
        await self.send_or_update_message(user_id, message,
            "🔐 SEND API HASH :",
            self.get_back_button())
    
    async def handle_api_hash(self, user_id: int, message: Message, message_text: str):
        if message_text == "🔙 BACK":
            session = self.get_user_session(user_id)
            session.state = UserState.ENTERING_API_ID
            await self.send_or_update_message(user_id, message,
                "🔑 SEND API ID :",
                self.get_back_button())
            return
        
        if not re.match(r'^[a-f0-9]{32}$', message_text, re.IGNORECASE):
            await self.send_or_update_message(user_id, message,
                "❌ INVALID API HASH\n\n🔐 SEND API HASH :",
                self.get_back_button())
            return
        
        session = self.get_user_session(user_id)
        session.api_hash = message_text
        session.state = UserState.ENTERING_PHONE
        await self.send_or_update_message(user_id, message,
            "📱 SEND PHONE NUMBER WITH COUNTRY CODE :\n\nExample: +919876543210",
            self.get_back_button())
    
    async def handle_phone(self, user_id: int, message: Message, message_text: str):
        if message_text == "🔙 BACK":
            session = self.get_user_session(user_id)
            session.state = UserState.ENTERING_API_HASH
            await self.send_or_update_message(user_id, message,
                "🔐 SEND API HASH :",
                self.get_back_button())
            return
        
        if not re.match(r'^\+\d{10,15}$', message_text):
            await self.send_or_update_message(user_id, message,
                "❌ INVALID PHONE NUMBER\n\n📱 SEND PHONE NUMBER WITH COUNTRY CODE :\nExample: +919876543210",
                self.get_back_button())
            return
        
        session = self.get_user_session(user_id)
        session.phone = message_text
        session.state = UserState.CONFIRM_PHONE
        await self.send_or_update_message(user_id, message,
            f"📱 IS THIS CORRECT NUMBER :\n\n{message_text}",
            self.get_yes_no_keyboard())
    
    async def handle_confirm_phone(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "✅ YES":
            try:
                await self.cleanup_client(user_id)
                
                app = Client(
                    name=f"user_{user_id}_{int(time.time())}",
                    api_id=int(session.api_id),
                    api_hash=session.api_hash,
                    in_memory=True,
                    device_model="Samsung Galaxy S23",
                    app_version="10.4.1",
                    system_version="Android 14",
                    lang_code="en"
                )
                
                await app.connect()
                
                sent_code = await app.send_code(phone_number=session.phone)
                
                session.phone_code_hash = sent_code.phone_code_hash
                session.client = app
                session.state = UserState.ENTERING_OTP
                
                await self.send_or_update_message(user_id, message,
                    "📨 ENTER OTP CODE SENT TO YOUR TELEGRAM :\n\n⚠️ IMPORTANT: DO NOT forward OTP from saved messages\nType the OTP code manually here",
                    self.get_back_button())
            
            except FloodWait as e:
                await self.send_or_update_message(user_id, message,
                    f"⏳ FLOOD WAIT {e.value}s",
                    self.get_main_menu_buttons())
                self.reset_user_session(user_id)
            
            except Exception as e:
                await self.send_or_update_message(user_id, message,
                    f"❌ ERROR: {str(e)[:100]}",
                    self.get_back_button())
                session.state = UserState.ENTERING_PHONE
        
        elif message_text == "❌ NO":
            session.state = UserState.ENTERING_PHONE
            await self.send_or_update_message(user_id, message,
                "📱 SEND PHONE NUMBER WITH COUNTRY CODE :\n\nExample: +919876543210",
                self.get_back_button())
    
    async def handle_otp(self, user_id: int, message: Message, message_text: str):
        if message_text == "🔙 BACK":
            session = self.get_user_session(user_id)
            session.state = UserState.CONFIRM_PHONE
            await self.send_or_update_message(user_id, message,
                f"📱 IS THIS CORRECT NUMBER :\n\n{session.phone}",
                self.get_yes_no_keyboard())
            return
        
        # Allow any OTP format (Telegram can send OTP like "12345", "12-345", etc.)
        otp_code = ''.join(filter(str.isdigit, message_text))
        
        if not otp_code or len(otp_code) < 4:
            await self.send_or_update_message(user_id, message,
                "❌ INVALID OTP\n\n📨 ENTER OTP CODE SENT TO YOUR TELEGRAM :",
                self.get_back_button())
            return
        
        session = self.get_user_session(user_id)
        
        try:
            # SIGN IN WITH OTP - NO CHAT READING
            await session.client.sign_in(
                phone_number=session.phone,
                phone_code_hash=session.phone_code_hash,
                phone_code=otp_code
            )
            
            await self.handle_successful_login(user_id, message)
        
        except SessionPasswordNeeded:
            session.state = UserState.ENTERING_2FA
            await self.send_or_update_message(user_id, message,
                "🔒 ENTER 2FA PASSWORD :",
                self.get_back_button())
        
        except (PhoneCodeInvalid, PhoneCodeExpired):
            await self.send_or_update_message(user_id, message,
                "❌ INVALID OR EXPIRED OTP\n\n📨 ENTER OTP CODE SENT TO YOUR TELEGRAM :",
                self.get_back_button())
        
        except Exception as e:
            error_msg = str(e)
            if "previously shared" in error_msg.lower():
                await self.send_or_update_message(user_id, message,
                    "❌ SAME ACCOUNT LOGIN ERROR\n\n⚠️ You cannot add the same account that is running this bot.\nPlease use a DIFFERENT Telegram account.",
                    self.get_main_menu_buttons())
                self.reset_user_session(user_id)
            else:
                await self.send_or_update_message(user_id, message,
                    f"❌ ERROR: {str(e)[:100]}",
                    self.get_back_button())
    
    async def handle_2fa(self, user_id: int, message: Message, message_text: str):
        if message_text == "🔙 BACK":
            session = self.get_user_session(user_id)
            session.state = UserState.ENTERING_OTP
            await self.send_or_update_message(user_id, message,
                "📨 ENTER OTP CODE :",
                self.get_back_button())
            return
        
        session = self.get_user_session(user_id)
        
        try:
            await session.client.check_password(password=message_text.strip())
            await self.handle_successful_login(user_id, message)
        
        except PasswordHashInvalid:
            await self.send_or_update_message(user_id, message,
                "❌ INVALID PASSWORD\n\n🔒 ENTER 2FA PASSWORD :",
                self.get_back_button())
        
        except Exception as e:
            await self.send_or_update_message(user_id, message,
                f"❌ ERROR: {str(e)[:100]}",
                self.get_back_button())
    
    async def handle_successful_login(self, user_id: int, message: Message):
        session = self.get_user_session(user_id)
        
        try:
            me = await session.client.get_me()
            username = f"@{me.username}" if me.username else f"User{me.id}"
            
            string_session = await session.client.export_session_string()
            await session.client.disconnect()
            
            success = self.db.add_account(
                user_id=user_id,
                account_id=me.id,
                phone=session.phone,
                username=username,
                string_session=string_session,
                api_id=session.api_id,
                api_hash=session.api_hash
            )
            
            if success:
                session.state = UserState.CONFIRM_ADD_MORE
                await self.send_or_update_message(user_id, message,
                    f"✅ ACCOUNT ADDED SUCCESSFULLY\n\nUsername: {username}\n\nADD MORE ACCOUNTS?",
                    self.get_yes_no_keyboard())
            else:
                await self.send_or_update_message(user_id, message,
                    "❌ DATABASE ERROR",
                    self.get_main_menu_buttons())
                session.state = UserState.MAIN_MENU
        
        except Exception as e:
            await self.send_or_update_message(user_id, message,
                f"❌ ERROR: {str(e)[:100]}",
                self.get_main_menu_buttons())
            session.state = UserState.MAIN_MENU
    
    async def handle_confirm_add_more(self, user_id: int, message: Message, message_text: str):
        if message_text == "✅ YES":
            self.reset_user_session(user_id)
            session = self.get_user_session(user_id)
            session.state = UserState.ENTERING_API_ID
            await self.send_or_update_message(user_id, message,
                "🔑 SEND API ID :",
                self.get_back_button())
        elif message_text == "❌ NO":
            await self.show_main_menu(user_id, message)
    
    async def show_manage_accounts(self, user_id: int, message: Message):
        session = self.get_user_session(user_id)
        session.state = UserState.MANAGE_ACCOUNTS
        
        user_accounts = self.db.get_user_accounts(user_id)
        
        if not user_accounts:
            await self.send_or_update_message(user_id, message,
                "❌ NO ACCOUNTS FOUND",
                self.get_main_menu_buttons())
            return
        
        account_list = []
        for idx, (_, username, _, _, _) in enumerate(user_accounts, 1):
            account_list.append(f"{idx}. {username}")
        
        accounts_text = "📋 ADDED ACCOUNTS LIST -\n\n" + "\n".join(account_list)
        
        await self.send_or_update_message(user_id, message,
            accounts_text,
            ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🗑️ REMOVE ACCOUNT")],
                    [KeyboardButton(text="🔙 BACK")]
                ],
                resize_keyboard=True
            ))
    
    async def handle_manage_accounts(self, user_id: int, message: Message, message_text: str):
        if message_text == "🗑️ REMOVE ACCOUNT":
            session = self.get_user_session(user_id)
            session.state = UserState.SELECT_ACCOUNT_REMOVE
            
            user_accounts = self.db.get_user_accounts(user_id)
            accounts = [username for _, username, _, _, _ in user_accounts]
            
            rows = []
            for i in range(0, len(accounts), 2):
                row_accounts = accounts[i:i+2]
                buttons = [KeyboardButton(text=acc) for acc in row_accounts]
                rows.append(buttons)
            rows.append([KeyboardButton(text="🔙 BACK")])
            
            buttons = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
            
            await self.send_or_update_message(user_id, message,
                "🗑️ SELECT ACCOUNT TO REMOVE :",
                buttons)
        
        elif message_text == "🔙 BACK":
            await self.show_main_menu(user_id, message)
    
    async def handle_select_account_remove(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        user_accounts = self.db.get_user_accounts(user_id)
        accounts = [username for _, username, _, _, _ in user_accounts]
        
        if message_text in accounts:
            session.selected_account = message_text
            session.state = UserState.REMOVE_CONFIRM
            await self.send_or_update_message(user_id, message,
                f"⚠️ CONFIRM REMOVAL\n\nREMOVE {message_text}?",
                self.get_yes_no_keyboard())
        elif message_text == "🔙 BACK":
            session.state = UserState.MANAGE_ACCOUNTS
            await self.show_manage_accounts(user_id, message)
    
    async def handle_remove_confirm(self, user_id: int, message: Message, message_text: str):
        session = self.get_user_session(user_id)
        
        if message_text == "✅ YES":
            deleted = self.db.delete_account(user_id, session.selected_account)
            
            if deleted:
                await self.send_or_update_message(user_id, message,
                    f"✅ ACCOUNT REMOVED\n\n{session.selected_account}",
                    self.get_main_menu_buttons())
            else:
                await self.send_or_update_message(user_id, message,
                    "❌ REMOVAL FAILED",
                    self.get_main_menu_buttons())
            
            session.state = UserState.MAIN_MENU
        
        elif message_text == "❌ NO":
            await self.show_main_menu(user_id, message)
    
    async def send_or_update_message(self, user_id: int, message: Message, text: str, keyboard: ReplyKeyboardMarkup):
        """Send or update message - keeps chat clean"""
        session = self.get_user_session(user_id)
        
        try:
            if session.last_message_id:
                try:
                    await message._client.edit_message_text(
                        chat_id=user_id,
                        message_id=session.last_message_id,
                        text=text,
                        reply_markup=keyboard
                    )
                    return
                except:
                    pass
            
            msg = await message.reply(text, reply_markup=keyboard)
            session.last_message_id = msg.id
        except Exception as e:
            logger.error(f"Error in send_or_update_message: {e}")
            msg = await message.reply(text, reply_markup=keyboard)
            session.last_message_id = msg.id
    
    async def start_sending_ads(self, user_id: int, message: Message):
        """Start sending ads"""
        session = self.get_user_session(user_id)
        
        if user_id in self.status_messages:
            try:
                await self.status_messages[user_id].delete()
            except:
                pass
        
        status_msg = await message.reply("🔄 INITIALIZING...", reply_markup=self.get_stop_keyboard())
        self.status_messages[user_id] = status_msg
        
        session.state = UserState.ADS_SENDING
        session.stop_requested = False
        
        if session.is_multi_account:
            task = asyncio.create_task(
                self.continuous_sending_multiple(
                    user_id=user_id,
                    account_usernames=list(session.selected_accounts),
                    send_delay=session.ads_delay,
                    set_delay_minutes=session.ads_set_delay,
                    bot_message=message
                )
            )
        else:
            task = asyncio.create_task(
                self.continuous_sending_single(
                    user_id=user_id,
                    account_username=session.selected_account,
                    send_delay=session.ads_delay,
                    set_delay_minutes=session.ads_set_delay,
                    bot_message=message
                )
            )
        
        session.sending_task = task
        self.active_tasks.add(task)
        task.add_done_callback(lambda t: self.active_tasks.discard(t))
    
    async def handle_ads_sending(self, user_id: int, message: Message, message_text: str):
        if message_text == "🛑 STOP SENDING":
            await self.handle_stop_button(user_id, message)
    
    async def update_status(self, user_id: int, text: str):
        """Update status message - single message update"""
        if user_id in self.status_messages:
            try:
                await self.status_messages[user_id].edit_text(text, reply_markup=self.get_stop_keyboard())
            except:
                try:
                    await self.status_messages[user_id].delete()
                except:
                    pass
                self.status_messages[user_id] = await self.bot_client.send_message(
                    user_id, text, reply_markup=self.get_stop_keyboard()
                )
    
    async def scan_all_groups(self, app: Client) -> List[Dict]:
        eligible_groups = []
        
        try:
            async for dialog in app.get_dialogs(limit=200):
                chat = dialog.chat
                
                if chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
                    try:
                        full_chat = await app.get_chat(chat.id)
                        
                        can_send = True
                        if hasattr(full_chat, 'permissions') and full_chat.permissions:
                            if not full_chat.permissions.can_send_messages:
                                can_send = False
                        
                        if can_send:
                            safety = ChatSafety(chat.id)
                            
                            if hasattr(full_chat, 'slow_mode_delay') and full_chat.slow_mode_delay:
                                safety.slow_mode_delay = full_chat.slow_mode_delay
                            
                            eligible_groups.append({
                                'id': chat.id,
                                'title': chat.title or f"Group {chat.id}",
                                'safety': safety,
                            })
                    except:
                        continue
        
        except Exception:
            pass
        
        return eligible_groups
    
    async def send_message_safely(self, app: Client, chat_id: int, source_message, safety: ChatSafety, behavior_engine: EliteBehaviorEngine) -> Tuple[bool, str, str]:
        """Send message with elite human-like behavior (Fixed Logic)"""
        try:
            if source_message.text:
                original_text = source_message.text
            elif source_message.caption:
                original_text = source_message.caption
            else:
                original_text = ""
            
            entities = source_message.entities or source_message.caption_entities
            
            # Check for duplicate content and modify
            if original_text and safety.is_duplicate_content(original_text):
                original_text = behavior_engine.modify_content(original_text)
            
            # Handle slow mode with strict waiting
            if safety.slow_mode_delay > 0:
                can_send, wait_time = safety.can_send_now()
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    await asyncio.sleep(random.uniform(0.2, 0.8))
            
            # Simulate elite human typing delay
            typing_delay = behavior_engine.calculate_delay(len(original_text) if original_text else 0)
            await asyncio.sleep(typing_delay)
            
            # Send message Logic
            message_hash = None
            if source_message.media:
                if original_text:
                    await app.send_cached_media(
                        chat_id=chat_id,
                        file_id=source_message.media.file_id,
                        caption=original_text,
                        caption_entities=entities
                    )
                    message_hash = hashlib.md5(original_text.encode()).hexdigest()
                    result_text = "✓ Text"
                else:
                    await app.send_cached_media(
                        chat_id=chat_id,
                        file_id=source_message.media.file_id
                    )
                    result_text = "✓ Media"
            elif original_text:
                await app.send_message(
                    chat_id=chat_id,
                    text=original_text,
                    entities=entities
                )
                message_hash = hashlib.md5(original_text.encode()).hexdigest()
                result_text = "✓ Text"
            else:
                return False, "no_content", ""
            
            safety.record_send(message_hash)
            return True, "sent", result_text
            
        except FloodWait as e:
            await asyncio.sleep(min(e.value or 10, 900))
            return False, "floodwait", ""
        
        except Exception as e:
            error_msg = str(e).lower()
            
            if "deleted" in error_msg or "delete" in error_msg:
                safety.record_deletion()
                return False, "deleted", ""
            elif "forbidden" in error_msg or "kicked" in error_msg:
                return False, "forbidden", ""
            else:
                safety.record_error()
                behavior_engine.increase_global_slowdown()
                return False, "error", ""
    
    async def continuous_sending_single(self, user_id: int, account_username: str, send_delay: int, set_delay_minutes: int, bot_message: Message):
        """Continuous sending for single account"""
        session = self.get_user_session(user_id)
        
        account_info = self.db.get_account_by_username(user_id, account_username)
        if not account_info:
            await self.update_status(user_id, f"❌ ACCOUNT NOT FOUND\n\n{account_username}")
            return
        
        account_id, string_session, api_id, api_hash = account_info
        
        app = Client(
            name=f"send_{user_id}_{account_id}",
            api_id=int(api_id),
            api_hash=api_hash,
            session_string=string_session,
            in_memory=True
        )
        
        try:
            await app.start()
            
            source_message = None
            async for message in app.get_chat_history("me", limit=1):
                source_message = message
                break
            
            if not source_message:
                await self.update_status(user_id, f"❌ NO MESSAGE FOUND")
                return
            
            behavior_engine = EliteBehaviorEngine()
            cycle_count = 0
            sent_groups = []
            
            while not session.stop_requested:
                cycle_count += 1
                
                await self.update_status(user_id, f"🔍 SCANNING GROUPS...\n\nAccount: {account_username}")
                
                groups = await self.scan_all_groups(app)
                
                if not groups:
                    await self.update_status(user_id, f"❌ NO GROUPS FOUND")
                    await asyncio.sleep(60)
                    continue
                
                random.shuffle(groups)
                total_groups = len(groups)
                sent_in_cycle = 0
                sent_groups = []
                
                # Update status with clean format
                status_text = f"{account_username}"
                await self.update_status(user_id, status_text)
                
                for i, group in enumerate(groups):
                    if session.stop_requested:
                        break
                    
                    success, reason, result_text = await self.send_message_safely(
                        app, group['id'], source_message, group['safety'], behavior_engine
                    )
                    
                    if success:
                        sent_in_cycle += 1
                        sent_groups.append(f"✓ {group['title'][:30]}")
                        
                        # Update status with sent groups
                        if len(sent_groups) <= 3:
                            status_text = f"{account_username}\n" + "\n".join(sent_groups)
                        else:
                            status_text = f"{account_username}\n" + "\n".join(sent_groups[-3:])
                        
                        await self.update_status(user_id, status_text)
                    
                    if i < len(groups) - 1 and send_delay > 0 and not session.stop_requested:
                        await asyncio.sleep(send_delay)
                
                if not session.stop_requested and set_delay_minutes > 0:
                    await self.update_status(user_id, f"✅ CYCLE {cycle_count} COMPLETED\n\n⏳ Next cycle in {set_delay_minutes} minutes...")
                    
                    remaining = set_delay_minutes * 60
                    while remaining > 0 and not session.stop_requested:
                        await asyncio.sleep(30)
                        remaining -= 30
                        
                        if remaining > 0 and not session.stop_requested:
                            await self.update_status(user_id, f"✅ CYCLE {cycle_count} COMPLETED\n\n⏳ Next cycle in {remaining//60}m {remaining%60}s...")
                
                if not session.stop_requested:
                    await asyncio.sleep(5)
            
            if session.stop_requested:
                await self.update_status(user_id, "⏹️ SENDING STOPPED")
        
        except Exception as e:
            await self.update_status(user_id, f"❌ ERROR\n\n{str(e)[:100]}")
        finally:
            try:
                await app.stop()
            except:
                pass
            
            if session.stop_requested:
                session.stop_requested = False
                await self.show_main_menu(user_id, bot_message)
    
    async def continuous_sending_multiple(self, user_id: int, account_usernames: List[str], send_delay: int, set_delay_minutes: int, bot_message: Message):
        """Continuous sending for multiple accounts"""
        session = self.get_user_session(user_id)
        
        random.shuffle(account_usernames)
        cycle_count = 0
        
        while not session.stop_requested:
            cycle_count += 1
            
            for account_idx, account_username in enumerate(account_usernames):
                if session.stop_requested:
                    break
                
                if account_idx > 0:
                    await self.update_status(user_id, f"🔄 SHUFFLING ACCOUNTS\n\nNext: {account_username}")
                    await asyncio.sleep(random.uniform(2, 5))
                
                account_info = self.db.get_account_by_username(user_id, account_username)
                if not account_info:
                    continue
                
                account_id, string_session, api_id, api_hash = account_info
                
                app = Client(
                    name=f"send_{user_id}_{account_id}",
                    api_id=int(api_id),
                    api_hash=api_hash,
                    session_string=string_session,
                    in_memory=True
                )
                
                try:
                    await app.start()
                    
                    source_message = None
                    async for message in app.get_chat_history("me", limit=1):
                        source_message = message
                        break
                    
                    if not source_message:
                        await app.stop()
                        continue
                    
                    behavior_engine = EliteBehaviorEngine()
                    
                    await self.update_status(user_id, f"🔍 SCANNING GROUPS...\n\nAccount: {account_username}")
                    
                    groups = await self.scan_all_groups(app)
                    
                    if not groups:
                        await app.stop()
                        continue
                    
                    random.shuffle(groups)
                    total_groups = len(groups)
                    sent_in_account = 0
                    sent_groups = []
                    
                    status_text = f"{account_username}"
                    await self.update_status(user_id, status_text)
                    
                    for i, group in enumerate(groups):
                        if session.stop_requested:
                            break
                        
                        success, reason, result_text = await self.send_message_safely(
                            app, group['id'], source_message, group['safety'], behavior_engine
                        )
                        
                        if success:
                            sent_in_account += 1
                            sent_groups.append(f"✓ {group['title'][:30]}")
                            
                            if len(sent_groups) <= 3:
                                status_text = f"{account_username}\n" + "\n".join(sent_groups)
                            else:
                                status_text = f"{account_username}\n" + "\n".join(sent_groups[-3:])
                            
                            await self.update_status(user_id, status_text)
                        
                        if i < len(groups) - 1 and send_delay > 0 and not session.stop_requested:
                            await asyncio.sleep(send_delay)
                    
                    await app.stop()
                    
                    if account_idx < len(account_usernames) - 1 and not session.stop_requested:
                        await asyncio.sleep(10)
                
                except Exception:
                    try:
                        await app.stop()
                    except:
                        pass
                    continue
            
            if not session.stop_requested and set_delay_minutes > 0:
                await self.update_status(user_id, f"✅ CYCLE {cycle_count} COMPLETED\n\n⏳ Next rotation in {set_delay_minutes} minutes...")
                
                remaining = set_delay_minutes * 60
                while remaining > 0 and not session.stop_requested:
                    await asyncio.sleep(30)
                    remaining -= 30
                    
                    if remaining > 0 and not session.stop_requested:
                        await self.update_status(user_id, f"✅ CYCLE {cycle_count} COMPLETED\n\n⏳ Next rotation in {remaining//60}m {remaining%60}s...")
        
        if session.stop_requested:
            await self.update_status(user_id, "⏹️ SENDING STOPPED")
            session.stop_requested = False
            await self.show_main_menu(user_id, bot_message)

async def main():
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 50)
        print("STARTING TELEGRAM BOT")
        print("=" * 50)
        
        bot = TelegramBot()
        await bot.start()
        
    except KeyboardInterrupt:
        print("\n⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

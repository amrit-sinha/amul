#!/usr/bin/env python3
"""
Amul Chocolate Whey Protein Stock Monitor
"""

import requests
import time
import os
import json
import random
import secrets
import argparse
from datetime import datetime
from typing import Dict, Optional


def load_dotenv(path: str = ".env") -> None:
    """Simple .env loader: sets variables into os.environ if not already set."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and os.getenv(key) is None:
                    os.environ[key] = val
    except Exception:
        pass


def load_config(path: str = "config.json") -> Dict:
    """Load JSON configuration for API (returns empty dict if not found)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class AmulProductMonitor:
    def __init__(
        self, telegram_bot_token: str, telegram_chat_id: str, api_config: Optional[Dict]
    ):
        # product id may be provided directly or via api_config
        self.product_id = api_config.get("product_id")
        self.api_url = api_config.get("api_url")
        self.check_interval = api_config.get("check_interval_minutes", int) * 60
        self.was_out_of_stock = True

        # Telegram config
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id

        # Use provided headers/params if present; load cookies from env first
        self.headers = api_config.get("headers", {}) if api_config else {}

        # Prefer cookies from COOKIES_JSON env var (secure storage); fallback to config
        cookies_from_env = os.getenv("COOKIES_JSON")
        if cookies_from_env:
            try:
                parsed = json.loads(cookies_from_env)
                self.cookies = parsed if isinstance(parsed, dict) else {}
            except Exception as e:
                print(f"Cookie error: {e}")

        # If params provided, ensure product id is updated only when the filter exists
        self.params = api_config.get("params", {}) if api_config else {}
        try:
            if isinstance(self.params, dict) and "filters[0][value][0]" in self.params:
                if self.params.get("filters[0][value][0]") != self.product_id:
                    self.params["filters[0][value][0]"] = self.product_id
        except Exception:
            pass

        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.cookies.update(self.cookies)

    def fetch_product(self) -> Optional[Dict]:
        """Fetch the specific product data"""

        try:
            timestamp = int(time.time() * 1000)

            # dynamic middle number and 64-hex suffix to resemble site tid format
            mid = random.randint(1, 999)
            suffix = secrets.token_hex(32)  # 64 hex chars
            self.session.headers["tid"] = f"{timestamp}:{mid}:{suffix}"

            response = self.session.get(self.api_url, params=self.params, timeout=30)
            response.raise_for_status()

            data = response.json()
            products = data.get("data", [])
            return products[0] if products else None

        except Exception as e:
            print(f"Error: {e}")
            return None

    def check_stock(self, product: Dict) -> bool:
        """Check if product is in stock"""

        if not product:
            return False
        return (
            product.get("inventory_quantity", 0) > 0
            and product.get("available", 0) == 1
        )

    def send_telegram_notification(self, product: Dict):
        """Send Telegram notification"""

        try:
            message = (
                f"🎉 *BACK IN STOCK*\n\n"
                f"✅ {product['name']}\n"
                f"📦 Stock: {product['inventory_quantity']} units\n"
                f"💰 Price: ₹{product['price']}\n"
                f"🔗 [Buy Now](https://shop.amul.com/en/product/{product['alias']})"
            )

            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            response = requests.post(
                url,
                json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
            )

            if response.status_code == 200:
                print(
                    f"{datetime.now().strftime('%H:%M:%S')} - Telegram notification sent"
                )
            else:
                print(
                    f"{datetime.now().strftime('%H:%M:%S')} - Failed to send Telegram notification"
                )

        except Exception as e:
            print(f"Telegram error: {e}")

    def run(self):
        """Main monitoring loop"""

        print(f"Monitor started - Checking every {self.check_interval / 60} minutes")

        # Initial check
        product = self.fetch_product()
        if product:
            is_in_stock = self.check_stock(product)
            self.was_out_of_stock = not is_in_stock
            status = "IN STOCK" if is_in_stock else "OUT OF STOCK"
            print(
                f"Initial status: {status} ({product.get('inventory_quantity', 0)} units)"
            )
        else:
            print("Failed to fetch product")
            return

        while True:
            try:
                product = self.fetch_product()

                if product:
                    is_in_stock = self.check_stock(product)

                    if is_in_stock and self.was_out_of_stock:
                        print(
                            f"{datetime.now().strftime('%H:%M:%S')} - 🎉 BACK IN STOCK!"
                        )
                        self.send_telegram_notification(product)
                        return
                    elif not is_in_stock:
                        self.was_out_of_stock = True
                        print(f"{datetime.now().strftime('%H:%M:%S')} - Out of stock")
                    else:
                        print(
                            f"{datetime.now().strftime('%H:%M:%S')} - In stock ({product.get('inventory_quantity', 0)} units)"
                        )

                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                print("\nMonitor stopped")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)


if __name__ == "__main__":
    # Load environment and config

    load_dotenv()
    config = load_config()

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in environment (.env)")
        raise SystemExit(1)

    api_config = config

    monitor = AmulProductMonitor(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, api_config)

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    args = parser.parse_args()

    if args.once:
        product = monitor.fetch_product()
        if product and monitor.check_stock(product):
            print(
                f"{datetime.now().isoformat()} - BACK IN STOCK -> sending notification"
            )
            monitor.send_telegram_notification(product)
        else:
            print(f"{datetime.now().isoformat()} - Not in stock")
    else:
        monitor.run()

#!/usr/bin/env python3
"""Amul Product Stock Monitor"""

import argparse
import json
import os
import random
import secrets
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

with open("config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)

PRODUCT_ID = CONFIG["product_id"]
API_URL = CONFIG["api_url"]
HEADERS = CONFIG.get("headers", {})
PARAMS = CONFIG.get("params", {})
INTERVAL = int(CONFIG.get("check_interval_minutes", 2)) * 60

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def cookie_header() -> str:
    raw = os.getenv("COOKIE", "").strip()
    if raw.lower().startswith("cookie:"):
        return raw.split(":", 1)[1].strip()
    return raw


def fetch_product() -> dict | None:
    cookie = cookie_header()
    if not cookie:
        print("Missing COOKIE")
        return None

    headers = {
        **HEADERS,
        "Cookie": cookie,
        "tid": f"{int(time.time() * 1000)}:{random.randint(1, 999)}:{secrets.token_hex(32)}",
    }

    try:
        resp = requests.get(API_URL, params=PARAMS, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

    products = data.get("data") or []
    if not products and data.get("paging", {}).get("total", 0) > 0:
        print("Empty product data, try refreshing COOKIE")
        return None

    return next((p for p in products if p.get("_id") == PRODUCT_ID), None)


def notify(product: dict) -> None:
    message = (
        f"🎉 *BACK IN STOCK*\n\n"
        f"✅ {product['name']}\n"
        f"📦 Stock: {product['inventory_quantity']} units\n"
        f"💰 Price: ₹{product['price']}\n"
        f"🔗 [Buy Now](https://shop.amul.com/en/product/{product['alias']})"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            },
            timeout=30,
        )
        status = "sent" if resp.ok else "failed"
        print(f"{datetime.now():%H:%M:%S} - Telegram notification {status}")
    except Exception as e:
        print(f"Telegram error: {e}")


def check_once() -> None:
    product = fetch_product()
    if not product:
        print(f"{datetime.now().isoformat()} - Product not found")
    elif product.get("available") == 1:
        print(f"{datetime.now().isoformat()} - BACK IN STOCK")
        notify(product)
    else:
        print(f"{datetime.now().isoformat()} - Not in stock")


def run_loop() -> None:
    print(f"Monitor started - checking every {INTERVAL // 60} minutes")

    product = fetch_product()
    if product:
        in_stock = product.get("available") == 1
        print(
            f"Initial status: {'IN STOCK' if in_stock else 'OUT OF STOCK'} "
            f"({product.get('inventory_quantity', 0)} units)"
        )
        if in_stock:
            notify(product)
    else:
        print("Initial status: Product not found")

    while True:
        try:
            time.sleep(INTERVAL)
            product = fetch_product()
            if not product:
                print(f"{datetime.now():%H:%M:%S} - Product not found")
            elif product.get("available") == 1:
                print(
                    f"{datetime.now():%H:%M:%S} - In stock "
                    f"({product.get('inventory_quantity', 0)} units)"
                )
                notify(product)
            else:
                print(f"{datetime.now():%H:%M:%S} - Out of stock")
        except KeyboardInterrupt:
            print("\nMonitor stopped")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    args = parser.parse_args()
    (check_once if args.once else run_loop)()

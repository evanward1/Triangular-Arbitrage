#!/usr/bin/env python3
"""
Test Coinbase Advanced Trading API authentication
"""
import os
from dotenv import load_dotenv
from coinbase.rest import RESTClient

# Load environment variables
load_dotenv()

api_key = os.getenv("EXCHANGE_API_KEY")
api_secret = os.getenv("EXCHANGE_API_SECRET")

print(f"API Key: {api_key[:50]}..." if api_key else "No API Key")
print(f"API Secret: {'***' if api_secret else 'No API Secret'}")

try:
    # Initialize the client
    client = RESTClient(api_key=api_key, api_secret=api_secret)

    # Test authentication by getting accounts
    accounts = client.get_accounts()
    print(f"✅ Authentication successful!")
    print(f"Found {len(accounts.accounts)} accounts")

    # Test getting products (markets)
    products = client.get_products()
    print(f"✅ Market data access successful!")
    print(f"Found {len(products.products)} trading pairs")

except Exception as e:
    print(f"❌ Authentication failed: {e}")
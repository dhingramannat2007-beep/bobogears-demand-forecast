import os
import schedule
import time
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# ─── Load credentials from .env ───────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

API_KEY      = os.getenv("BLINKIT_API_KEY")
SELLER_ID    = os.getenv("BLINKIT_SELLER_ID")
FULL_COOKIE  = os.getenv("BLINKIT_FULL_COOKIE")

# ─── Settings ─────────────────────────────────────────────────────────────────
API_URL       = "https://seller.blinkit.com/seller-hub/api/inventories/v1/view"
OUTPUT_FILE   = "/Users/mannat/Desktop/blinkit_order_recommendations.xlsx"
SAFETY_BUFFER = 0.15  # 15% extra buffer on top of predicted demand


# ─── Step 1: Fetch inventory data from Blinkit API ────────────────────────────
def fetch_inventory():
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Fetching inventory from Blinkit...")

    headers = {
        "x-api-key":       API_KEY,
        "x-gr-seller-id":  SELLER_ID,
        "Cookie":          FULL_COOKIE,
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15",
        "Referer":         "https://seller.blinkit.com/dashboard/inventory?inventory=stock_in_hand",
        "app_client":      "seller-dashboard-web",
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "same-origin",
    }

    params = {
        "sort":           "newest_first",
        "secondary_sort": "last_7_days",
        "page":           0,
    }

    all_items = []
    page = 0

    # Blinkit paginates results — keep fetching until no more pages
    while True:
        params["page"] = page
        response = requests.get(API_URL, headers=headers, params=params)

        if response.status_code == 401:
            print("❌ Authentication failed — your access_token may have expired.")
            print("   Update BLINKIT_ACCESS_TOKEN in the .env file and try again.")
            return None

        if response.status_code != 200:
            print(f"❌ API error: {response.status_code} — {response.text[:200]}")
            return None

        data = response.json()

        # Extract items from the response
        items = data.get("data", {}).get("inventories", [])
        if not items:
            break

        all_items.extend(items)
        print(f"   Fetched page {page} — {len(items)} products")
        page += 1

    print(f"   Total products fetched: {len(all_items)}")
    return all_items


# ─── Step 2: Parse API response into a clean dataframe ────────────────────────
def parse_inventory(items):
    rows = []
    for item in items:
        # Each item may span multiple warehouses
        for warehouse in item.get("warehouses", [item]):
            rows.append({
                "Item Name":               item.get("name", ""),
                "UPC":                     item.get("upc", ""),
                "Warehouse":               warehouse.get("warehouse_name", ""),
                "Total Sellable Inventory": warehouse.get("total_sellable", 0),
                "Units Sold Last 30 Days": warehouse.get("last_30_days", 0),
                "Min Limit":               warehouse.get("min_inventory", None),
                "Max Limit":               warehouse.get("max_inventory", None),
            })

    df = pd.DataFrame(rows)
    return df


# ─── Step 3: Derive min/max if Blinkit doesn't return them ────────────────────
def derive_limits(df):
    # If Blinkit's API doesn't return min/max, we calculate smart defaults:
    # Min = at least 2 weeks worth of sales (to never run out mid-month)
    # Max = 2x predicted monthly demand (don't overstock)
    if df["Min Limit"].isnull().all():
        df["Min Limit"] = (df["Units Sold Last 30 Days"] / 2).round().astype(int)
    if df["Max Limit"].isnull().all():
        df["Max Limit"] = (df["Units Sold Last 30 Days"] * 2).round().astype(int)
    return df


# ─── Step 4: Run the forecast and calculate order quantities ──────────────────
def run_forecast(df):
    # Predicted demand = last month's sales + 15% safety buffer
    df["Predicted Demand (Next Month)"] = (
        df["Units Sold Last 30 Days"] * (1 + SAFETY_BUFFER)
    ).round().astype(int)

    # Ideal order = how many units we're short by
    df["Ideal Order"] = (
        df["Predicted Demand (Next Month)"] - df["Total Sellable Inventory"]
    ).clip(lower=0)

    # Final order = clamp ideal order within Blinkit's min/max limits
    df["Final Order Quantity"] = df.apply(
        lambda row: int(max(row["Min Limit"], min(row["Ideal Order"], row["Max Limit"])))
        if row["Ideal Order"] > 0 else 0,
        axis=1
    )

    return df


# ─── Step 5: Save results to Excel ────────────────────────────────────────────
def save_results(df):
    output_cols = [
        "Item Name",
        "UPC",
        "Warehouse",
        "Total Sellable Inventory",
        "Units Sold Last 30 Days",
        "Min Limit",
        "Max Limit",
        "Predicted Demand (Next Month)",
        "Ideal Order",
        "Final Order Quantity",
    ]

    df[output_cols].to_excel(OUTPUT_FILE, index=False)
    print(f"✅ Recommendations saved to '{OUTPUT_FILE}'")
    print(df[output_cols].to_string())


# ─── Main job: runs every 12 hours ────────────────────────────────────────────
def run_job():
    items = fetch_inventory()
    if items is None:
        return

    df = parse_inventory(items)
    df = derive_limits(df)
    df = run_forecast(df)
    save_results(df)


# ─── Scheduler ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("BoboGears x Blinkit Demand Forecast")
    print("=====================================")
    print("Running now, then every 12 hours...")

    # Run immediately on start
    run_job()

    # Then schedule every 12 hours
    schedule.every(12).hours.do(run_job)

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute if it's time to run

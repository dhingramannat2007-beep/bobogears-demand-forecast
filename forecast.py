import os
import pandas as pd

# ─── Settings ─────────────────────────────────────────────────────────────────
STOCK_FILE    = "/Users/mannat/Desktop/bobo_gear/InventoryData.xlsx"          # Blinkit "Stock on Hand" report
LIMITS_FILE   = "/Users/mannat/Desktop/bobo_gear/limits_template.xlsx"        # Filled-in min/max template (optional)
OUTPUT_FILE   = "/Users/mannat/Desktop/bobo_gear/order_recommendations.xlsx"  # Result

SAFETY_BUFFER = 0.15  # order 15% extra on top of last month's sales as a cushion


# ─── Step 1: Read the stock report ────────────────────────────────────────────
def read_stock():
    raw = pd.read_excel(STOCK_FILE, header=2)
    df = pd.DataFrame({
        "Item Name":                raw["Item Name"],
        "UPC":                      raw["UPC"],
        "Warehouse":                raw["Warehouse Facility Name"],
        "Total Sellable Inventory": raw["Total sellable"],
        "Units Sold Last 30 Days":  raw["Last 30 days"],
    })
    return df


# ─── Step 2: Attach min/max limits ────────────────────────────────────────────
def attach_limits(df):
    # Read the manager's limits template and keep ONLY the rows where they
    # actually filled in a Min and Max — those are the warehouses they want
    # to send stock to this time. Everything else is ignored.
    limits = pd.read_excel(LIMITS_FILE)[["UPC", "Warehouse", "Min Limit", "Max Limit"]]

    limits["Min Limit"] = pd.to_numeric(limits["Min Limit"], errors="coerce")
    limits["Max Limit"] = pd.to_numeric(limits["Max Limit"], errors="coerce")

    # Drop any row where Min or Max was left blank
    limits = limits.dropna(subset=["Min Limit", "Max Limit"])
    limits["Min Limit"] = limits["Min Limit"].astype(int)
    limits["Max Limit"] = limits["Max Limit"].astype(int)

    # Inner merge -> only keep stock rows that have a matching filled-in limit
    df = df.merge(limits, on=["UPC", "Warehouse"], how="inner")

    if df.empty:
        print("⚠️  No limits filled in yet. Open limits_template.xlsx and enter")
        print("    Min and Max for the warehouses you want to send stock to.")

    return df


# ─── Step 3: Forecast and calculate the order ─────────────────────────────────
def run_forecast(df):
    # Predicted demand = last month's sales + safety buffer
    df["Predicted Demand"] = (
        df["Units Sold Last 30 Days"] * (1 + SAFETY_BUFFER)
    ).round().astype(int)

    # Ideal order = how many units we're short by (never negative)
    df["Ideal Order"] = (df["Predicted Demand"] - df["Total Sellable Inventory"]).clip(lower=0)

    # Final order = keep the ideal order within the min/max limits.
    # Only clamp when we actually need to order something.
    df["Final Order Quantity"] = df.apply(
        lambda r: int(max(r["Min Limit"], min(r["Ideal Order"], r["Max Limit"])))
        if r["Ideal Order"] > 0 else 0,
        axis=1,
    )
    return df


# ─── Step 4: Save ─────────────────────────────────────────────────────────────
def main():
    df = read_stock()
    df = attach_limits(df)
    df = run_forecast(df)

    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Done! Recommendations saved to '{OUTPUT_FILE}'")
    print(df.to_string())


if __name__ == "__main__":
    main()

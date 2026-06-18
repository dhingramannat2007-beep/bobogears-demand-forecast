import pandas as pd

# ─── Settings ─────────────────────────────────────────────────────────────────
STOCK_FILE     = "/Users/mannat/Desktop/bobo_gear/InventoryData.xlsx"   # Blinkit "Stock on Hand" report
TEMPLATE_FILE  = "/Users/mannat/Desktop/bobo_gear/limits_template.xlsx"  # Output template to fill in


# Reads the stock report and creates a blank template listing every
# product + warehouse, with empty Min/Max columns for the manager to fill.
def main():
    raw = pd.read_excel(STOCK_FILE, header=2)

    template = pd.DataFrame({
        "Item Name":  raw["Item Name"],
        "UPC":        raw["UPC"],
        "Warehouse":  raw["Warehouse Facility Name"],
        "Min Limit":  "",   # manager fills this
        "Max Limit":  "",   # manager fills this
    })

    template.to_excel(TEMPLATE_FILE, index=False)
    print(f"Template created at '{TEMPLATE_FILE}'")
    print("Open it, type the Min and Max limit for each warehouse, and save.")


if __name__ == "__main__":
    main()

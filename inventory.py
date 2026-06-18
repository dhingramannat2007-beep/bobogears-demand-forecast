import csv
import os
from datetime import date

PRODUCTS_FILE = "products.csv"
SALES_FILE = "sales.csv"


# ─── Setup ───────────────────────────────────────────────────────────────────

def setup():
    """Create files if they don't exist yet."""
    if not os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["product_code", "product_name", "warehouse"])

    if not os.path.exists(SALES_FILE):
        with open(SALES_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "product_code", "product_name", "quantity_sold"])


# ─── Helper Functions ─────────────────────────────────────────────────────────

def load_products():
    products = []
    with open(PRODUCTS_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)
    return products


def product_exists(code):
    products = load_products()
    for p in products:
        if p["product_code"].lower() == code.lower():
            return True
    return False


# ─── Features ────────────────────────────────────────────────────────────────

def add_product():
    print("\n--- Add New Product ---")
    name = input("Product Name: ").strip()
    code = input("Product Code: ").strip()
    warehouse = input("Warehouse Location: ").strip()

    if product_exists(code):
        print(f"❌ Product with code '{code}' already exists.")
        return

    with open(PRODUCTS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([code, name, warehouse])

    print(f"✅ Product '{name}' added successfully.")


def view_products():
    print("\n--- All Products ---")
    products = load_products()

    if not products:
        print("No products added yet.")
        return

    print(f"{'Code':<15} {'Name':<30} {'Warehouse':<20}")
    print("-" * 65)
    for p in products:
        print(f"{p['product_code']:<15} {p['product_name']:<30} {p['warehouse']:<20}")


def log_sale():
    print("\n--- Log Today's Sale ---")
    view_products()

    code = input("\nEnter Product Code to log sale for: ").strip()

    if not product_exists(code):
        print(f"❌ Product with code '{code}' not found. Please add it first.")
        return

    try:
        quantity = int(input("Quantity Sold Today: ").strip())
    except ValueError:
        print("❌ Please enter a valid number.")
        return

    products = load_products()
    product_name = ""
    for p in products:
        if p["product_code"].lower() == code.lower():
            product_name = p["product_name"]
            break

    today = date.today().strftime("%Y-%m-%d")

    with open(SALES_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([today, code, product_name, quantity])

    print(f"✅ Logged {quantity} units sold for '{product_name}' on {today}.")


def view_sales():
    print("\n--- Sales History ---")

    with open(SALES_FILE, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("No sales logged yet.")
        return

    print(f"{'Date':<15} {'Code':<15} {'Product':<30} {'Qty Sold':<10}")
    print("-" * 70)
    for row in rows:
        print(f"{row['date']:<15} {row['product_code']:<15} {row['product_name']:<30} {row['quantity_sold']:<10}")


def view_summary():
    print("\n--- Sales Summary (Total per Product) ---")

    with open(SALES_FILE, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("No sales logged yet.")
        return

    summary = {}
    for row in rows:
        key = row["product_code"]
        if key not in summary:
            summary[key] = {"name": row["product_name"], "total": 0}
        summary[key]["total"] += int(row["quantity_sold"])

    print(f"{'Code':<15} {'Product':<30} {'Total Sold':<10}")
    print("-" * 55)
    for code, data in summary.items():
        print(f"{code:<15} {data['name']:<30} {data['total']:<10}")


# ─── Main Menu ────────────────────────────────────────────────────────────────

def main():
    setup()
    print("\n============================")
    print("   BoboGears Inventory Tool ")
    print("============================")

    while True:
        print("\nWhat do you want to do?")
        print("1. Add a product")
        print("2. View all products")
        print("3. Log today's sales")
        print("4. View sales history")
        print("5. View sales summary")
        print("6. Exit")

        choice = input("\nEnter choice (1-6): ").strip()

        if choice == "1":
            add_product()
        elif choice == "2":
            view_products()
        elif choice == "3":
            log_sale()
        elif choice == "4":
            view_sales()
        elif choice == "5":
            view_summary()
        elif choice == "6":
            print("\nGoodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter a number between 1-6.")


if __name__ == "__main__":
    main()

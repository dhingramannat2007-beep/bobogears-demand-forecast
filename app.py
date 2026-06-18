import io
import pandas as pd
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# BoboGears Demand Forecast — web app
#
# What it does:
#   1. Upload one or more monthly SALES reports  -> learns demand trend per product
#   2. Upload the current STOCK ON HAND report   -> current stock per warehouse
#   3. Fill Min/Max only for the warehouses you want to send to
#   4. Get the recommended order quantity per warehouse, downloadable as Excel
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="BoboGears Demand Forecast", page_icon="📦", layout="wide")
st.title("📦 BoboGears Demand Forecast")
st.caption("Upload your Blinkit reports, pick the warehouses to restock, and get order quantities.")

# Sidebar control
SAFETY_BUFFER = st.sidebar.slider(
    "Safety buffer (extra stock cushion)", 0.0, 0.50, 0.15, 0.05,
    help="Order this much % extra on top of predicted demand, so you don't run out."
)
st.sidebar.markdown(
    "**How the forecast works**\n\n"
    "- Uses your monthly sales to spot if each product is growing or shrinking\n"
    "- Recent months count more than older ones (weighted average)\n"
    "- Final order always stays within the Min/Max you set per warehouse"
)


# ─── Helpers ──────────────────────────────────────────────────────────────────
def read_sales(files):
    """Combine uploaded monthly sales reports into one table of units sold."""
    frames = []
    for f in files:
        d = pd.read_excel(f)[["UPC", "Product Name", "Order Date", "Quantity"]].copy()
        d["Order Date"] = pd.to_datetime(d["Order Date"])
        d["Month"] = d["Order Date"].dt.to_period("M").astype(str)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def product_trend(sales):
    """
    For each product, measure whether it is trending up or down by comparing its
    latest full month against its recent average. Returns a 'Trend Multiplier':
      > 1  -> product is growing, nudge the forecast up
      < 1  -> product is declining, nudge the forecast down
    The latest (possibly partial) month is ignored so the average stays fair.
    The multiplier is capped to a sensible range so a noisy month can't swing
    the order wildly.
    """
    monthly = sales.groupby(["UPC", "Month"])["Quantity"].sum().reset_index()

    all_months = sorted(monthly["Month"].unique())
    full_months = all_months[:-1] if len(all_months) > 1 else all_months

    rows = []
    for upc, g in monthly.groupby("UPC"):
        g = g[g["Month"].isin(full_months)].sort_values("Month")
        if g.empty:
            continue
        vals = g["Quantity"].tolist()
        avg = sum(vals) / len(vals)
        last_month = vals[-1]
        multiplier = (last_month / avg) if avg else 1.0
        multiplier = max(0.7, min(multiplier, 1.4))  # keep it sensible
        rows.append({"UPC": upc, "Trend Multiplier": round(multiplier, 3)})

    return pd.DataFrame(rows)


def read_stock(file):
    """Read the Stock on Hand report (real headers are on the 3rd row)."""
    raw = pd.read_excel(file, header=2)
    return pd.DataFrame({
        "Item Name":      raw["Item Name"],
        "UPC":            raw["UPC"],
        "Warehouse":      raw["Warehouse Facility Name"],
        "Current Stock":  pd.to_numeric(raw["Total sellable"], errors="coerce").fillna(0).astype(int),
        "Sold Last 30d":  pd.to_numeric(raw["Last 30 days"], errors="coerce").fillna(0).astype(int),
    })


# ─── Step 1: Upload sales reports ─────────────────────────────────────────────
st.header("1. Upload monthly sales reports")
st.write("You can upload several months at once — more months = better predictions.")
sales_files = st.file_uploader(
    "Sales reports (Excel)", type=["xlsx"], accept_multiple_files=True, key="sales"
)

# ─── Step 2: Upload current stock ─────────────────────────────────────────────
st.header("2. Upload current stock on hand")
stock_file = st.file_uploader("Stock on Hand report (Excel)", type=["xlsx"], key="stock")


if sales_files and stock_file:
    sales = read_sales(sales_files)
    trend = product_trend(sales)
    stock = read_stock(stock_file)

    # Attach each product's trend multiplier (default 1.0 if no sales history)
    stock = stock.merge(trend, on="UPC", how="left")
    stock["Trend Multiplier"] = stock["Trend Multiplier"].fillna(1.0)

    # Predicted demand per warehouse:
    #   warehouse's own recent sales × product trend × safety buffer
    stock["Predicted Demand"] = (
        stock["Sold Last 30d"] * stock["Trend Multiplier"] * (1 + SAFETY_BUFFER)
    ).round().astype(int)

    # Show the demand picture
    st.success(f"Loaded {len(sales)} orders across {sales['Month'].nunique()} month(s).")
    with st.expander("See monthly demand per product"):
        pivot = sales.groupby(["Product Name", "Month"])["Quantity"].sum().unstack(fill_value=0)
        st.dataframe(pivot, use_container_width=True)

    # ─── Step 3: Pick warehouses + enter limits ──────────────────────────────
    st.header("3. Set Min / Max for warehouses you want to restock")
    st.write("Only rows where you fill **both** Min and Max will get a recommendation.")

    editor = stock[["Item Name", "UPC", "Warehouse", "Current Stock",
                    "Sold Last 30d", "Predicted Demand"]].copy()
    editor["Min Limit"] = None
    editor["Max Limit"] = None

    edited = st.data_editor(
        editor,
        use_container_width=True,
        height=400,
        disabled=["Item Name", "UPC", "Warehouse", "Current Stock",
                  "Sold Last 30d", "Predicted Demand"],
        key="limits_editor",
    )

    # ─── Step 4: Generate recommendations ────────────────────────────────────
    if st.button("Generate order recommendations", type="primary"):
        df = edited.copy()
        df["Min Limit"] = pd.to_numeric(df["Min Limit"], errors="coerce")
        df["Max Limit"] = pd.to_numeric(df["Max Limit"], errors="coerce")

        # keep only the warehouses the manager filled in
        df = df.dropna(subset=["Min Limit", "Max Limit"])

        if df.empty:
            st.warning("Fill in Min and Max for at least one warehouse, then try again.")
        else:
            df["Min Limit"] = df["Min Limit"].astype(int)
            df["Max Limit"] = df["Max Limit"].astype(int)

            # ideal order = how many units short (never negative)
            df["Ideal Order"] = (df["Predicted Demand"] - df["Current Stock"]).clip(lower=0)

            # final order = keep ideal order within Min/Max
            df["Final Order Quantity"] = df.apply(
                lambda r: int(max(r["Min Limit"], min(r["Ideal Order"], r["Max Limit"])))
                if r["Ideal Order"] > 0 else 0,
                axis=1,
            )

            st.header("✅ Recommended orders")
            st.dataframe(df, use_container_width=True)

            total = int(df["Final Order Quantity"].sum())
            st.metric("Total units to order", total)

            # downloadable Excel
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False)
            st.download_button(
                "⬇️ Download as Excel",
                data=buffer.getvalue(),
                file_name="order_recommendations.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
else:
    st.info("⬆️ Upload at least one sales report and the current stock report to begin.")

import io
import re
import pandas as pd
import streamlit as st


def normalize_wh(name):
    """
    Reduce a warehouse name to its core 'city code' (e.g. 'hyderabad h3') so that
    the name typed into the bookmarklet matches the inventory file even when the
    inventory file adds boilerplate like ' - Feeder', ' - Feeder Warehouse', or
    ' - SR'. We only strip those known noise words — the meaningful part (city +
    code) must still match exactly, so 'Mumbai M12' will NOT match 'Mumbai M10'.
    """
    s = str(name).lower().replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)                  # drop punctuation
    s = re.sub(r"\b(feeder|warehouse|sr)\b", " ", s)   # drop boilerplate words
    s = re.sub(r"\s+", " ", s).strip()
    return s

# ──────────────────────────────────────────────────────────────────────────────
# BoboGears Demand Forecast — web app
#
# What it does:
#   1. Upload one or more monthly SALES reports   -> learns demand trend per product
#   2. Upload the current INVENTORY report        -> "Last 30 days" demand per warehouse
#   3. Upload the Min/Max LIMIT files              -> per-product Min/Max + live stock
#      (these come from the "Get Blinkit Limits" bookmarklet — one CSV per warehouse)
#   4. Get the recommended order quantity per product per warehouse, as Excel
#
# Note on the limits: Blinkit gives a Min/Max for EACH product in EACH warehouse,
# so we clamp every product against its OWN limit (not one limit per warehouse).
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="BoboGears Demand Forecast", page_icon="📦", layout="wide")

# ─── Colour theme (Navy / Teal / Sky Blue / Beige) ────────────────────────────
st.markdown("""
<style>
    /* palette: navy #2F4156, teal #567C8D, sky #C8D9E6, beige #F5EFEB */
    .stApp { background-color: #FFFFFF; }
    h1, h2, h3 { color: #2F4156 !important; font-family: Georgia, serif; }
    .stCaption, .st-emotion-cache-1rsyhoq { color: #567C8D; }

    /* primary buttons */
    .stButton > button, .stDownloadButton > button {
        background-color: #2F4156; color: #FFFFFF;
        border: none; border-radius: 8px; font-weight: 600;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background-color: #567C8D; color: #FFFFFF;
    }

    /* sidebar in beige */
    section[data-testid="stSidebar"] { background-color: #F5EFEB; }

    /* info / success boxes tinted to palette */
    .stAlert { border-radius: 8px; }

    /* metric accent */
    div[data-testid="stMetricValue"] { color: #567C8D; }

    /* uploaders with sky-blue dashed border */
    section[data-testid="stFileUploaderDropzone"] {
        background-color: #F5EFEB; border: 2px dashed #C8D9E6;
    }
</style>
""", unsafe_allow_html=True)

st.title("📦 BoboGears Demand Forecast")
st.caption("Upload your Blinkit reports + the limit files, and get order quantities per warehouse.")

# Sidebar control
SAFETY_BUFFER = st.sidebar.slider(
    "Safety buffer (extra stock cushion)", 0.0, 0.50, 0.15, 0.05,
    help="Order this much % extra on top of predicted demand, so you don't run out."
)
st.sidebar.markdown(
    "**How the forecast works**\n\n"
    "- Uses your monthly sales to spot if each product is growing or shrinking\n"
    "- Predicts each warehouse's demand from its own recent sales\n"
    "- Final order stays within Blinkit's Min/Max for that exact product"
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
    out = pd.concat(frames, ignore_index=True)
    out["UPC"] = out["UPC"].astype(str).str.strip()
    return out


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


def read_inventory(file):
    """
    Read the Inventory report (real headers are on the 3rd row).
    We use this ONLY for each warehouse's recent demand ("Last 30 days").
    Current stock now comes from the live limit files instead, but we keep
    the inventory stock as a fallback in case a product is missing from them.
    """
    raw = pd.read_excel(file, header=2)
    df = pd.DataFrame({
        "Item Name":            raw["Item Name"],
        "UPC":                  raw["UPC"],
        "Warehouse":            raw["Warehouse Facility Name"],
        "Inv Stock (fallback)": pd.to_numeric(raw["Total sellable"], errors="coerce").fillna(0).astype(int),
        "Sold Last 30d":        pd.to_numeric(raw["Last 30 days"], errors="coerce").fillna(0).astype(int),
    })
    df["UPC"] = df["UPC"].astype(str).str.strip()
    df["Warehouse"] = df["Warehouse"].astype(str).str.strip()
    return df


def read_limits(files):
    """
    Combine the Min/Max CSV files produced by the 'Get Blinkit Limits' bookmarklet.
    Each file is one warehouse's products with: Warehouse, UPC, Product,
    CurrentStock, Min, Max. We keep only rows that have BOTH a Min and a Max
    (blank ones — e.g. products you're not restocking — are skipped).
    """
    frames = []
    for f in files:
        frames.append(pd.read_csv(f))
    lim = pd.concat(frames, ignore_index=True)

    lim["UPC"] = lim["UPC"].astype(str).str.strip()
    lim["Warehouse"] = lim["Warehouse"].astype(str).str.strip()
    lim["Min"] = pd.to_numeric(lim["Min"], errors="coerce")
    lim["Max"] = pd.to_numeric(lim["Max"], errors="coerce")
    lim["CurrentStock"] = pd.to_numeric(lim.get("CurrentStock"), errors="coerce")

    lim = lim.dropna(subset=["Min", "Max"]).copy()
    lim["Min"] = lim["Min"].astype(int)
    lim["Max"] = lim["Max"].astype(int)
    return lim


# ─── Step 1: Upload sales reports ─────────────────────────────────────────────
st.header("1. Upload monthly sales reports")
st.write("You can upload several months at once — more months = better predictions.")
sales_files = st.file_uploader(
    "Sales reports (Excel)", type=["xlsx"], accept_multiple_files=True, key="sales"
)

# ─── Step 2: Upload inventory report (for demand history) ─────────────────────
st.header("2. Upload the inventory report")
st.caption("Used to read each warehouse's recent demand (the 'Last 30 days' column). "
           "This is the engine behind the prediction — it is NOT used for current stock.")
inventory_file = st.file_uploader("Inventory report (Excel)", type=["xlsx"], key="inventory")

# ─── Step 3: Upload the Min/Max limit files (from the bookmarklet) ─────────────
st.header("3. Upload the Min/Max limit files")
st.caption("These are the CSV files from the 'Get Blinkit Limits' bookmarklet — "
           "one file per warehouse you want to restock. They carry each product's "
           "Min/Max limit and its live current stock. Upload as many as you like.")
limit_files = st.file_uploader(
    "Limit files (CSV)", type=["csv"], accept_multiple_files=True, key="limits"
)


if sales_files and inventory_file and limit_files:
    sales = read_sales(sales_files)
    trend = product_trend(sales)
    inv = read_inventory(inventory_file)
    lim = read_limits(limit_files)

    st.success(
        f"Loaded {len(sales)} orders across {sales['Month'].nunique()} month(s), "
        f"and limits for {lim['Warehouse'].nunique()} warehouse(s)."
    )
    with st.expander("See monthly demand per product"):
        pivot = sales.groupby(["Product Name", "Month"])["Quantity"].sum().unstack(fill_value=0)
        st.dataframe(pivot, use_container_width=True)

    # Attach each product's trend multiplier (default 1.0 if no sales history)
    inv = inv.merge(trend, on="UPC", how="left")
    inv["Trend Multiplier"] = inv["Trend Multiplier"].fillna(1.0)

    # Combine: the limit files decide WHICH (warehouse, product) rows we order for.
    # We match warehouses on a NORMALIZED name (city + code) so the bookmarklet's
    # short name lines up with the inventory file's '... - Feeder' style names,
    # while still keeping genuinely different warehouses (M12 vs M10) apart.
    lim["_wh_key"] = lim["Warehouse"].map(normalize_wh)
    inv["_wh_key"] = inv["Warehouse"].map(normalize_wh)

    merged = lim.merge(
        inv[["_wh_key", "UPC", "Sold Last 30d", "Trend Multiplier", "Inv Stock (fallback)"]],
        on=["_wh_key", "UPC"], how="left",
    )

    # Rows from the limit files that found NO match in the inventory file.
    # Usually this means the warehouse name you typed into the bookmarklet
    # doesn't exactly match the inventory file's "Warehouse Facility Name".
    unmatched = merged[merged["Sold Last 30d"].isna()]
    if not unmatched.empty:
        st.warning(
            "Some limit rows didn't match the inventory file (so they have no demand "
            "history and can't be forecast). This is almost always a warehouse-name "
            "mismatch — the name typed into the bookmarklet must match the inventory "
            "file's 'Warehouse Facility Name' exactly."
        )
        with st.expander("Show the rows that didn't match"):
            st.dataframe(
                unmatched[["Warehouse", "UPC", "Product"]], use_container_width=True
            )
        st.caption("Warehouse names in your limit files: "
                   + ", ".join(sorted(lim["Warehouse"].unique())))
        st.caption("Warehouse names in your inventory file: "
                   + ", ".join(sorted(inv["Warehouse"].unique())))

    # Keep only rows we can actually forecast (have demand history).
    df = merged[merged["Sold Last 30d"].notna()].copy()

    if df.empty:
        st.error("No limit rows matched the inventory file, so nothing can be forecast yet. "
                 "Check the warehouse-name mismatch note above.")
    else:
        df["Sold Last 30d"] = df["Sold Last 30d"].astype(int)

        # Current stock: prefer the live figure from the limit file; if for some
        # reason it's blank, fall back to the inventory file's stock.
        df["Current Stock"] = df["CurrentStock"].where(
            df["CurrentStock"].notna(), df["Inv Stock (fallback)"]
        ).fillna(0).astype(int)

        # Predicted demand per warehouse:
        #   warehouse's own recent sales × product trend × safety buffer
        df["Predicted Demand"] = (
            df["Sold Last 30d"] * df["Trend Multiplier"] * (1 + SAFETY_BUFFER)
        ).round().astype(int)

        # Ideal order = how many units short (never negative)
        df["Ideal Order"] = (df["Predicted Demand"] - df["Current Stock"]).clip(lower=0)

        # Final order = clamp the ideal order within THIS product's Min/Max.
        # Only clamp when we actually need to order something.
        df["Final Order Quantity"] = df.apply(
            lambda r: int(max(r["Min"], min(r["Ideal Order"], r["Max"])))
            if r["Ideal Order"] > 0 else 0,
            axis=1,
        )

        # Tidy column order/names for display + download
        result = df[[
            "Warehouse", "Product", "UPC", "Current Stock", "Sold Last 30d",
            "Trend Multiplier", "Predicted Demand", "Min", "Max",
            "Ideal Order", "Final Order Quantity",
        ]].rename(columns={"Min": "Min Limit", "Max": "Max Limit"})
        result = result.sort_values(["Warehouse", "Product"]).reset_index(drop=True)

        st.header("✅ Recommended orders")
        st.dataframe(result, use_container_width=True)

        total = int(result["Final Order Quantity"].sum())
        st.metric("Total units to order", total)

        # downloadable Excel
        buffer = io.BytesIO()
        result.to_excel(buffer, index=False)
        st.download_button(
            "⬇️ Download as Excel",
            data=buffer.getvalue(),
            file_name="order_recommendations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info("⬆️ Upload your sales reports, the inventory report, and at least one "
            "Min/Max limit file to begin.")

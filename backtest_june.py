"""
Backtest for June: use March + April + May to predict June.

NOTE: the June file only covers 1-17 June (17 days), not the full month.
To compare fairly, we scale June's actual sales up to a full-month estimate
(units so far / 17 days * 30 days). It's an estimate, not exact.
"""
import pandas as pd

REPORTS = "/Users/mannat/Desktop/bobo_gear/reports/"
SAFETY_BUFFER = 0.15
JUNE_DAYS_SO_FAR = 17
DAYS_IN_MONTH = 30


def load_month(path):
    return pd.read_excel(path)[["UPC", "Product Name", "Quantity"]]


def predict_next(history_months):
    monthly = pd.concat([m.assign(MonthIdx=i) for i, m in enumerate(history_months)])
    monthly = monthly.groupby(["UPC", "MonthIdx"])["Quantity"].sum().reset_index()
    preds = []
    for upc, g in monthly.groupby("UPC"):
        vals = g.sort_values("MonthIdx")["Quantity"].tolist()
        avg = sum(vals) / len(vals)
        last = vals[-1]
        mult = max(0.7, min((last / avg) if avg else 1.0, 1.4))
        preds.append({"UPC": upc, "Predicted June": round(last * mult * (1 + SAFETY_BUFFER))})
    return pd.DataFrame(preds)


def main():
    march = load_month(REPORTS + "sales-report-march2026.xlsx")
    april = load_month(REPORTS + "sales-report-april2026.xlsx")
    may   = load_month(REPORTS + "sales-report-may2026.xlsx")
    june  = load_month(REPORTS + "sales-report-mtd-17-06-2026-currentmonth.xlsx")

    pred = predict_next([march, april, may])

    # June so far, scaled up to a full-month estimate
    june_actual = june.groupby("UPC")["Quantity"].sum().reset_index()
    june_actual["June so far (17d)"] = june_actual["Quantity"]
    june_actual["June full-month est"] = (
        june_actual["Quantity"] * DAYS_IN_MONTH / JUNE_DAYS_SO_FAR
    ).round().astype(int)
    june_actual = june_actual.drop(columns="Quantity")

    names = pd.concat([march, april, may, june])[["UPC", "Product Name"]].drop_duplicates()

    result = (
        pred.merge(june_actual, on="UPC", how="outer")
            .merge(names, on="UPC", how="left")
            .fillna(0)
    )

    result["Error"] = (result["Predicted June"] - result["June full-month est"]).abs()
    result["Accuracy %"] = (
        100 * (1 - result["Error"] / result["June full-month est"].replace(0, 1))
    ).clip(lower=0).round(1)

    cols = ["Product Name", "Predicted June", "June so far (17d)",
            "June full-month est", "Accuracy %"]
    print("\nBacktest — predicted June (from Mar+Apr+May) vs June pace:\n")
    print(result[cols].to_string(index=False))

    overall = 100 * (1 - result["Error"].sum() / result["June full-month est"].sum())
    print(f"\nOverall accuracy: {overall:.1f}%")
    print("(June actual is estimated from 17 days, so treat this as a rough check.)")


if __name__ == "__main__":
    main()

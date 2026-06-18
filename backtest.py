"""
Backtest: does the forecast actually work?

Idea: pretend we're at the end of April. Use ONLY March + April sales to
predict May demand per product. Then compare against what REALLY sold in May.
The script prints an accuracy score so you don't have to compare by hand.
"""
import pandas as pd

REPORTS = "/Users/mannat/Desktop/bobo_gear/reports/"
SAFETY_BUFFER = 0.15


def load_month(path):
    d = pd.read_excel(path)[["UPC", "Product Name", "Quantity"]]
    return d


def predict_next(history_months):
    """Same trend logic as the app: latest month vs recent average."""
    monthly = pd.concat(
        [m.assign(MonthIdx=i) for i, m in enumerate(history_months)]
    )
    monthly = monthly.groupby(["UPC", "MonthIdx"])["Quantity"].sum().reset_index()

    preds = []
    for upc, g in monthly.groupby("UPC"):
        vals = g.sort_values("MonthIdx")["Quantity"].tolist()
        avg = sum(vals) / len(vals)
        last = vals[-1]
        mult = max(0.7, min((last / avg) if avg else 1.0, 1.4))
        # predicted demand = last month scaled by trend + safety buffer
        predicted = round(last * mult * (1 + SAFETY_BUFFER))
        preds.append({"UPC": upc, "Predicted May": predicted})
    return pd.DataFrame(preds)


def main():
    march = load_month(REPORTS + "sales-report-march2026.xlsx")
    april = load_month(REPORTS + "sales-report-april2026.xlsx")
    may   = load_month(REPORTS + "sales-report-may2026.xlsx")

    # Predict May using only March + April
    pred = predict_next([march, april])

    # What actually sold in May
    actual = may.groupby("UPC")["Quantity"].sum().reset_index()
    actual = actual.rename(columns={"Quantity": "Actual May"})

    names = pd.concat([march, april, may])[["UPC", "Product Name"]].drop_duplicates()

    result = (
        pred.merge(actual, on="UPC", how="outer")
            .merge(names, on="UPC", how="left")
            .fillna(0)
    )

    # accuracy per product = 100% - (error / actual)
    result["Error"] = (result["Predicted May"] - result["Actual May"]).abs()
    result["Accuracy %"] = (
        100 * (1 - result["Error"] / result["Actual May"].replace(0, 1))
    ).clip(lower=0).round(1)

    cols = ["Product Name", "Predicted May", "Actual May", "Error", "Accuracy %"]
    print("\nBacktest — predicted May (from Mar+Apr) vs what actually sold:\n")
    print(result[cols].to_string(index=False))

    overall = 100 * (1 - result["Error"].sum() / result["Actual May"].sum())
    print(f"\nOverall accuracy: {overall:.1f}%")
    print("(Higher is better. 80%+ is solid for this little data.)")


if __name__ == "__main__":
    main()

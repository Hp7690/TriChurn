"""Download the IBM Telco Customer Churn sample dataset into ml/data/raw/."""
import urllib.request
from pathlib import Path

URL = (
    "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/"
    "master/data/Telco-Customer-Churn.csv"
)
DEST = Path(__file__).resolve().parents[1] / "ml" / "data" / "raw" / "telco_churn.csv"

if __name__ == "__main__":
    DEST.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(URL, DEST)  # noqa: S310 - fixed https URL
    print(f"Saved {DEST} ({DEST.stat().st_size / 1024:.0f} KB)")

import pandas as pd
from src.detect.conversion_collapse import detect_conversion_collapses

alerts = detect_conversion_collapses()
df = pd.DataFrame(alerts)

print("=== Alerts by source/medium ===")
print(df.groupby(["source", "medium"])["detected_at"].count())

print("\n=== Severity breakdown ===")
print(df["severity"].value_counts())
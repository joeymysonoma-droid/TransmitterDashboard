from pathlib import Path

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)
for needle in ['case"refresh"', "refresh~", "function wss_onmessage", 'case"login"']:
    idx = text.find(needle)
    print("====", needle, idx)
    if idx >= 0:
        print(text[idx : idx + 1500])
        print()

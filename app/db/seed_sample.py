from pathlib import Path
import json, os

def main():
    Path("data/hts").mkdir(parents=True, exist_ok=True)
    Path("data/rulings").mkdir(parents=True, exist_ok=True)
    Path("data/golden").mkdir(parents=True, exist_ok=True)

    hts_sample = [
        {"code":"3926.90.99","description":"Other articles of plastics","duty_rate":"5%","chapter":39,"notes":""},
        {"code":"4202.92.90","description":"Travel, sports and similar bags","duty_rate":"17.6%","chapter":42,"notes":""},
    ]
    Path("data/hts/sample.json").write_text(json.dumps(hts_sample, indent=2))

    ruling_sample = {
        "ruling_id":"NY N000000",
        "hts_codes":["3926.90.99"],
        "url":"https://rulings.cbp.gov/",
        "text":"Sample ruling text for development only.",
        "date":"2019-01-01"
    }
    Path("data/rulings/NY_N000000.json").write_text(json.dumps(ruling_sample, indent=2))

    golden_csv = "sku,description,expected_hts\nS1,Plastic gadget housing,3926.90.99\nS2,Travel backpack,4202.92.90\n"
    Path("data/golden/golden_set.csv").write_text(golden_csv)

    print("Seed complete. Wrote sample HTS, one ruling, and golden_set.csv")

if __name__ == "__main__":
    main()

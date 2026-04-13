import csv
from collections import Counter

INPUT_CSV = r"newdata\steam_top_100_20251230_to_2026331_range_with_tags.csv"


def normalize_date(date_str):
    parts = date_str.strip().split("-")
    if len(parts) != 3:
        return date_str.strip()
    y, m, d = parts
    return f"{int(y)}-{int(m)}-{int(d)}"


def count_tags_by_date(input_csv, target_date):
    tag_counter = Counter()
    matched_rows = 0

    with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            row_date = normalize_date(row.get("date", ""))
            if row_date != normalize_date(target_date):
                continue

            matched_rows += 1
            tags_text = row.get("tags", "").strip()

            if not tags_text:
                continue

            tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
            for tag in tags:
                tag_counter[tag] += 1

    return tag_counter, matched_rows


def save_tag_counts(output_csv, tag_counter):
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["tag", "count"])

        for tag, count in tag_counter.most_common():
            writer.writerow([tag, count])


def main():
    target_date = input("請輸入日期 (例如 2026-3-31): ").strip()
    output_csv = rf"newdata\tag_count_{target_date.replace('-', '_')}.csv"

    tag_counter, matched_rows = count_tags_by_date(INPUT_CSV, target_date)

    print(f"\n日期: {target_date}")
    print(f"符合筆數: {matched_rows}")
    print("-" * 30)

    if matched_rows == 0:
        print("找不到指定日期的資料。")
        return

    for tag, count in tag_counter.most_common():
        print(f"{tag}: {count}")

    save_tag_counts(output_csv, tag_counter)
    print("-" * 30)
    print(f"統計結果已存到: {output_csv}")


if __name__ == "__main__":
    main()
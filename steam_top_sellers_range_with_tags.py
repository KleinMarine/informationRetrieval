import asyncio
import csv
import os
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://store.steampowered.com/charts/topsellers/TW/{}"

#設定日期區間 格式如"2026-03-31"
START_DATE = input("開始日期 (YYYY-MM-DD): ")
END_DATE = input("結束日期 (YYYY-MM-DD): ")

# 輸出檔案
start_str = START_DATE.replace("-", "")
end_str = END_DATE.replace("-", "")
OUTPUT_CSV = fr"newdata\steam_top_100_{start_str}_to_{end_str}_range_with_tags.csv"


def generate_dates(start, end, step_days=7):
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    dates = []
    current = end_dt

    while current >= start_dt:
        dates.append(f"{current.year}-{current.month}-{current.day}")
        current -= timedelta(days=step_days)

    return dates


async def scrape_top100_one_page(page, url, date):
    print(f"\n抓取榜單：{date}")

    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)

    # 點「查看所有 100 項」
    try:
        await page.click("text=查看所有 100 項", timeout=5000)
        await page.wait_for_timeout(3000)
    except Exception:
        print("找不到「查看所有 100 項」按鈕，可能已經展開或頁面不同")

    # 等資料載入
    await page.wait_for_function(
        """
        () => {
            const rows = document.querySelectorAll(
                'a[href*="/app/"], a[href*="/sub/"], a[href*="/bundle/"]'
            );
            return rows.length >= 100;
        }
        """,
        timeout=15000
    )

    items = await page.evaluate(
        """
        () => {
            const rows = Array.from(
                document.querySelectorAll('a[href*="/app/"], a[href*="/sub/"], a[href*="/bundle/"]')
            );
            const result = [];

            for (const a of rows) {
                let name = (a.innerText || "").trim();
                let href = a.href || "";

                if (!name || !href) continue;

                result.push({
                    name: name,
                    url: href
                });
            }

            return result;
        }
        """
    )

    return [{"date": date, "rank": i + 1, **item} for i, item in enumerate(items)]


async def handle_age_gate(page):
    await page.wait_for_timeout(1500)

    try:
        year_select = page.locator("#ageYear")
        view_button = page.locator("#view_product_page_btn, a#view_product_page_btn, .btnv6_blue_hoverfade")

        if await year_select.count() > 0:
            print("偵測到年齡確認頁，正在自動通過...")

            month = page.locator("#ageMonth")
            day = page.locator("#ageDay")

            if await day.count() > 0:
                await day.select_option("1")
            if await month.count() > 0:
                await month.select_option("January")
            await year_select.select_option("1990")

            if await view_button.count() > 0:
                await view_button.first.click()
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(2500)

    except Exception as e:
        print(f"年齡確認處理失敗：{e}")


async def scrape_tags_from_game_page(page, url: str):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)

        await handle_age_gate(page)

        # 抓遊戲名稱
        title = ""
        title_selectors = [
            ".apphub_AppName",
            "#appHubAppName",
            ".game_title_area h1",
        ]

        for selector in title_selectors:
            loc = page.locator(selector)
            if await loc.count() > 0:
                text = (await loc.first.inner_text()).strip()
                if text:
                    title = text
                    break

        # 抓標籤
        tags = await page.evaluate(
            """
            () => {
                const tagNodes = Array.from(document.querySelectorAll('a.app_tag'));
                const tags = [];

                for (const node of tagNodes) {
                    const text = (node.innerText || "").trim();
                    if (!text) continue;
                    if (text === "+") continue;
                    if (!tags.includes(text)) {
                        tags.push(text);
                    }
                }

                return tags;
            }
            """
        )

        return {
            "title": title,
            "tags": tags,
            "success": True,
            "error": ""
        }

    except PlaywrightTimeoutError:
        return {
            "title": "",
            "tags": [],
            "success": False,
            "error": "timeout"
        }
    except Exception as e:
        return {
            "title": "",
            "tags": [],
            "success": False,
            "error": str(e)
        }


async def main():
    dates = generate_dates(START_DATE, END_DATE)
    all_top100_rows = []
    final_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        # 一個 page 抓榜單
        ranking_page = await browser.new_page(viewport={"width": 1400, "height": 2200})

        for date in dates:
            url = BASE_URL.format(date)

            try:
                data = await scrape_top100_one_page(ranking_page, url, date)
                all_top100_rows.extend(data)
                print(f"{date} 抓到 {len(data)} 筆")
            except Exception as e:
                print(f"{date} 榜單抓取失敗：{e}")

        await ranking_page.close()

        print(f"\n榜單抓取完成，共 {len(all_top100_rows)} 筆，開始抓 tags...")

        # 另一個 page 抓遊戲頁
        game_page = await browser.new_page()
        total = len(all_top100_rows)

        for idx, row in enumerate(all_top100_rows, 1):
            date = row.get("date", "")
            rank = row.get("rank", "")
            name = row.get("name", "")
            url = row.get("url", "")

            print(f"[{idx}/{total}] 正在抓：{date} #{rank} {name}")

            data = await scrape_tags_from_game_page(game_page, url)

            final_results.append({
                "date": date,
                "rank": rank,
                "name_from_top100": name,
                "title_from_page": data["title"],
                "url": url,
                "tags": ", ".join(data["tags"]),
                "tag_count": len(data["tags"]),
                "success": data["success"],
                "error": data["error"]
            })

            await game_page.wait_for_timeout(1200)

        await game_page.close()
        await browser.close()

    os.makedirs("newdata", exist_ok=True)

    with open(OUTPUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "date",
            "rank",
            "name_from_top100",
            "title_from_page",
            "url",
            "tags",
            "tag_count",
            "success",
            "error",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(final_results)

    print(f"\n完成！已輸出：{OUTPUT_CSV}")
    print(f"共 {len(final_results)} 筆資料")


if __name__ == "__main__":
    asyncio.run(main())
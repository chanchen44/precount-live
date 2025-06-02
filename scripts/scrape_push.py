## busan_edu_crawl.py
"""
Playwright‑기반 – 부산교육감(2025‑04‑02 재·보궐) 개표구별 결과 1회 수집 스크립트

✓  검색 전 URL → http://info.nec.go.kr/main/showDocument.xhtml?electionId=0020250402&topMenuId=VC&secondMenuId=VCCP08
✓  검색 버튼 클릭 후 전환되는 URL → http://info.nec.go.kr/electioninfo/electionInfo_report.xhtml
✓  표는 페이지 분할 없음 (16000 row 이하)
✓  필요열 : 읍면동명 / 투표구명 / 선거인수 / 투표수 / 후보별 득표수(전체 칼럼) / 무효투표수 / 기권자수
✓  출력 : CSV (UTF‑8‑sig)  ▸ `busan_edu_20250402.csv`

> pip install playwright bs4 pandas
> playwright install chromium
"""
from pathlib import Path
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

URL_START = (
    "http://info.nec.go.kr/main/showDocument.xhtml?"
    "electionId=0020250402&topMenuId=VC&secondMenuId=VCCP08"
)
OUTPUT = Path(__file__).with_name("busan_edu_20250402.csv")

# column map(한글→영문) – 필요에 따라 수정
COLS = {
    "읍면동명": "town",
    "투표구명": "precinct",
    "선거인수": "voter_cnt",
    "투표수": "total_votes",
    "정순태": "cand1",  # 예시 후보명, 실제 컬럼명 확인 후 수정
    "최현욱": "cand2",
    "강복수": "cand3",
    "계": "valid_votes",
    "무효투표": "invalid_votes",
    "기권자": "abstain",
}

def scrape_table_html(page):
    """실제 표를 포함한 HTML을 반환"""
    page.goto(URL_START, timeout=0)

    # 시도·구군 드롭다운 선택
    page.select_option("#cityCode", "2600")  # 부산광역시
    page.select_option("#sggCityCode", "220")  # 중구 (임의, 표 전체 필요 없으므로 무시)

    # 검색 클릭
    page.click("input#btnSearch")

    # table 로딩 대기 후 HTML 추출
    page.wait_for_selector("table#table01")
    return page.inner_html("table#table01")

def parse_table(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    header = [th.text.strip() for th in soup.select_one("tr").find_all("th")]
    rows = []
    for tr in soup.select("tr")[1:]:
        rows.append([td.text.strip().replace(",", "") for td in tr.find_all("td")])

    df = pd.DataFrame(rows, columns=header)

    # 필요한 열만, 한글→영문 rename
    df = df[[k for k in COLS.keys() if k in df.columns]].rename(columns=COLS)
    # 숫자형 변환
    for col in df.columns[2:]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    return df

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
        ))
        html = scrape_table_html(page)
        browser.close()

    df = parse_table(html)
    df.insert(0, "crawl_ts", datetime.utcnow().isoformat())
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"[✓] saved {len(df):,} rows -> {OUTPUT}")

if __name__ == "__main__":
    main()

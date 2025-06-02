from playwright.sync_api import sync_playwright, expect
from bs4 import BeautifulSoup

def crawl_once():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
                "Gecko/20100101 Firefox/123.0"
            )
        )

        # ① 홈 이동
        page.goto("http://info.nec.go.kr/", wait_until="domcontentloaded")

        # ② 상단-메뉴: [최근선거] 클릭
        page.click("text=최근선거")

        # ③ 상단 탭: [두-개표] 클릭
        page.click("text=투·개표")          # 메뉴에 정확히 표시된 텍스트 확인

        # ④ 왼쪽 사이드메뉴: [개표단위별 개표결과]
        page.click("text=개표단위별 개표결과")

        # ⑤ 시도 드롭다운 → 부산광역시(2600)
        page.select_option("select#cityCode", "2600")

        # ⑥ 구·시·군 드롭다운 → (전체) 선택 시 value='' 또는 '000'
        page.select_option("select#sggCityCode", "")   # 전체 구군

        # ⑦ 검색 버튼 클릭
        page.click("input#btnSearch")

        # ⑧ 표 로딩 대기 (최대 60 초)
        page.wait_for_selector("table#table01", timeout=60_000)

        # ⑨ HTML 추출
        html = page.inner_html("table#table01")
        browser.close()

    # ⑩ BeautifulSoup 파싱 (간략 예시)
    soup = BeautifulSoup(html, "lxml")
    headers = [th.get_text(strip=True) for th in soup.select_one("tr").find_all("th")]
    rows = []
    for tr in soup.select("tr")[1:]:
        rows.append([td.get_text(strip=True) for td in tr.find_all("td")])
    print(headers[:7])
    print(rows[:2])

if __name__ == "__main__":
    crawl_once()

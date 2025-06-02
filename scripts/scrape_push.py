from playwright.sync_api import sync_playwright, expect
from bs4 import BeautifulSoup

def crawl_once():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # STEP 1: 진입
        page.goto("http://info.nec.go.kr/main/showDocument.xhtml?electionId=0020250402&topMenuId=VC&secondMenuId=VCCP08")

        # STEP 2: 페이지 로딩 및 요소 기다리기
        page.wait_for_timeout(3000)  # JS가 드롭다운 그릴 시간 확보
        page.wait_for_selector("#cityCode", state="visible", timeout=10000)

        # STEP 3: 드롭다운 선택
        page.select_option("#cityCode", "2600")     # 부산광역시
        page.wait_for_timeout(1000)                 # 두 번째 셀렉트 로딩 대기
        page.select_option("#sggCityCode", "0")     # 중구

        # STEP 4: 검색 버튼 클릭 및 테이블 로딩 대기
        page.click("input#btnSearch")
        page.wait_for_selector("table#table01", timeout=10000)

        # STEP 5: HTML 파싱
        html = page.inner_html("table#table01")
        browser.close()

        # STEP 6: BeautifulSoup 파싱
        soup = BeautifulSoup(html, "html.parser")
        rows = [
            [td.get_text(strip=True) for td in tr.find_all("td")]
            for tr in soup.select("tbody > tr")
        ]

        # STEP 7: 결과 출력 (또는 저장)
        for row in rows:
            print(row)

if __name__ == "__main__":
    crawl_once()

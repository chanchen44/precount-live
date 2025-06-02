from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

URL = "http://info.nec.go.kr/main/showDocument.xhtml?electionId=0020250402&topMenuId=VC&secondMenuId=VCCP08"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto(URL, wait_until="networkidle")

    # 드롭다운 선택
    page.select_option("#cityCode", "2600")     # 부산광역시
    page.select_option("#sggCityCode", "")      # 전체

    page.click("input#btnSearch")
    page.wait_for_selector("table#table01", timeout=60000)

    html = page.inner_html("table#table01")
    soup = BeautifulSoup(html, "html.parser")

    for row in soup.select("tr")[1:]:  # 첫 줄은 헤더
        print([cell.get_text(strip=True) for cell in row.select("td")])

    browser.close()

import json, os, time, requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
UP_URL  = os.environ["UP_URL"]
UP_TOK  = os.environ["UP_TOKEN"]
HEADERS = {"Authorization": f"Bearer {UP_TOK}"}

def fetch_dom():
    with sync_playwright() as p:
        page = p.chromium.launch(headless=True).new_page()
        page.goto("http://info.nec.go.kr/bizcommon/selectbox/selectbox_citybyvotesDetail_EB21.do", timeout=0)
        page.wait_for_selector("#table01")
        return page.inner_html("#table01")

def parse(html):
    soup = BeautifulSoup(html, "lxml")
    nums = lambda s: int(s.replace(",", "")) if s else 0
    rows = soup.select("tr")[1:]
    total1 = total2 = 0
    for tr in rows:
        t = tr.find_all("td")
        total1 += nums(t[2].text)
        total2 += nums(t[3].text)
    return {"c1": total1, "c2": total2, "ts": int(time.time())}

data = parse(fetch_dom())
requests.post(f"{UP_URL}/set/totals", headers=HEADERS, json=data)

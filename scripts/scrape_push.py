import os
import time
import json # JSON 직렬화를 위해 추가
import redis # Redis 사용을 위해 추가
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup

# --- Upstash Redis로 데이터를 전송하는 함수 ---
def push_to_upstash_redis(data, endpoint, port, password, key_name):
    """
    추출된 데이터를 Upstash Redis에 JSON 문자열로 저장합니다.
    """
    if not data:
        print("No data to push to Redis.")
        return

    print(f"Attempting to push data to Upstash Redis (Endpoint: {endpoint}, Key: {key_name})...")
    
    try:
        # Upstash Redis 클라이언트 초기화
        r = redis.Redis(
            host=endpoint,
            port=int(port), # 포트 번호는 정수형이어야 함
            password=password,
            ssl=True # Upstash Redis는 SSL/TLS 연결을 사용
        )
        
        # 데이터 Ping 테스트 (연결 확인)
        r.ping()
        print("Successfully connected to Upstash Redis.")
        
        # Python 딕셔너리를 JSON 문자열로 변환
        json_data = json.dumps(data, ensure_ascii=False) # 한글 깨짐 방지
        
        # Redis에 데이터 저장 (지정한 key_name 사용)
        r.set(key_name, json_data)
        print(f"Data successfully pushed to Upstash Redis with key '{key_name}'.")
        
    except redis.exceptions.ConnectionError as e:
        print(f"Redis ConnectionError: Could not connect to Upstash Redis at {endpoint}:{port}. Error: {e}")
        raise # 오류를 다시 발생시켜 GitHub Action 실패 처리
    except Exception as e:
        print(f"An unexpected error occurred during Redis operation: {e}")
        raise # 오류를 다시 발생시켜 GitHub Action 실패 처리

def crawl_once():
    # GitHub Actions 워크플로우에서 설정한 환경 변수 가져오기
    UPSTASH_REDIS_ENDPOINT = os.environ.get("UPSTASH_REDIS_ENDPOINT")
    UPSTASH_REDIS_PORT = os.environ.get("UPSTASH_REDIS_PORT")
    UPSTASH_REDIS_PASSWORD = os.environ.get("UPSTASH_REDIS_PASSWORD")
    REDIS_KEY_NAME = "live_election_data" # 여기서 키 이름 지정

    scraped_data = None
    page = None
    browser = None
    screenshot_dir = "playwright-screenshots" 
    os.makedirs(screenshot_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    # 필수 환경 변수 확인
    if not all([UPSTASH_REDIS_ENDPOINT, UPSTASH_REDIS_PORT, UPSTASH_REDIS_PASSWORD]):
        print("Error: Upstash Redis connection details (endpoint, port, password) are not fully configured in environment variables.")
        print(f"Endpoint: {UPSTASH_REDIS_ENDPOINT}, Port: {UPSTASH_REDIS_PORT}, Password Set: {'Yes' if UPSTASH_REDIS_PASSWORD else 'No'}")
        # 환경 변수가 없으면 데이터 푸시를 시도하지 않고 종료하거나, 오류를 발생시킬 수 있습니다.
        # 여기서는 오류를 발생시켜 GitHub Action에서 문제를 인지하도록 합니다.
        raise ValueError("Missing Upstash Redis credentials in environment variables.")

    with sync_playwright() as p:
        try:
            print("Launching browser...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
                    "Gecko/20100101 Firefox/123.0"
                ),
                viewport={'width': 1280, 'height': 1024} 
            )
            page = context.new_page()
            page.set_default_timeout(30_000)

            target_page_url = "http://info.nec.go.kr/main/showDocument.xhtml?electionId=0020250402&topMenuId=VC&secondMenuId=VCCP08"
            print(f"Step 1: Navigating to target page: {target_page_url}")
            page.goto(target_page_url, wait_until="domcontentloaded", timeout=60_000)
            print("Step 1: Target page navigation completed.")
            page.wait_for_timeout(1000)

            print("Step 2: Selecting '시도' dropdown (부산광역시)...")
            page.select_option("select#cityCode", "2600")
            print("Step 2: '시도' (부산광역시) selected.")
            page.wait_for_timeout(1000)

            print("Step 3: Selecting '구시군' dropdown (전체)...")
            page.select_option("select#sggCityCode", "")
            print("Step 3: '구시군' (전체) selected.")
            page.wait_for_timeout(500)

            print("Step 4: Clicking search button...")
            page.locator("span.btnSearch > a:has-text('검색')").click()
            print("Step 4: Search button clicked.")

            print("Step 5: Waiting for table (table#table01) to load after search...")
            page.wait_for_selector("table#table01", timeout=60_000)
            print("Step 5: Result table loaded.")

            print("Step 6: Extracting HTML from table#table01...")
            html = page.inner_html("table#table01")
            print("Step 6: HTML extraction completed.")

            print("Step 7: Parsing HTML with BeautifulSoup...")
            soup = BeautifulSoup(html, "lxml")
            
            first_row = soup.select_one("tr")
            if not first_row:
                raise ValueError("Parsing Error: Could not find the first row in the table HTML.")
            
            headers = [th.get_text(strip=True) for th in first_row.find_all("th")]
            if not headers:
                raise ValueError("Parsing Error: Could not parse headers from the table.")

            rows = []
            for tr in soup.select("tr")[1:]:
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cols:
                    rows.append(cols)
            
            scraped_data = {"headers": headers, "rows": rows} # 수집된 데이터
            print(f"Headers extracted: {headers[:7]}...")
            print(f"Number of data rows extracted: {len(rows)}")
            if rows:
                print(f"Sample data row: {rows[0][:7]}...")
            print("Step 7: HTML parsing completed.")

        except TimeoutError as e:
            print(f"TimeoutError occurred: {e}")
            if page:
                screenshot_path = os.path.join(screenshot_dir, f"error_timeout_{timestamp}.png")
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                    print(f"Screenshot saved to {screenshot_path}")
                except Exception as se:
                    print(f"Could not save screenshot: {se}")
            raise 
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            if page:
                screenshot_path = os.path.join(screenshot_dir, f"error_unexpected_{timestamp}.png")
                try:
                    page.screenshot(path=screenshot_path, full_page=True)
                    print(f"Screenshot saved to {screenshot_path}")
                except Exception as se:
                    print(f"Could not save screenshot: {se}")
            raise
        finally:
            if browser:
                print("Closing browser...")
                browser.close()
                print("Browser closed.")

    # --- 수집된 데이터가 있을 경우 Upstash Redis에 푸시 ---
    if scraped_data:
        print(f"Step 8: Attempting to push data to Upstash Redis with key '{REDIS_KEY_NAME}'...")
        try:
            push_to_upstash_redis(
                scraped_data, 
                UPSTASH_REDIS_ENDPOINT, 
                UPSTASH_REDIS_PORT, 
                UPSTASH_REDIS_PASSWORD,
                REDIS_KEY_NAME
            )
            print("Step 8: Data push to Upstash Redis finished.")
        except Exception as e:
            # 데이터 푸시 실패 시에도 오류를 기록하고 GitHub Action이 실패하도록 처리
            print(f"Error during data push to Upstash Redis: {e}")
            raise
    else:
        print("Skipping Upstash Redis push: No data was scraped (possibly due to an earlier error or empty result).")

if __name__ == "__main__":
    current_timestamp = time.strftime("%Y%m%d-%H%M%S")
    print(f"Starting crawl_once function at {current_timestamp}...")
    crawl_once()
    print(f"crawl_once function finished at {time.strftime('%Y%m%d-%H%M%S')}.")

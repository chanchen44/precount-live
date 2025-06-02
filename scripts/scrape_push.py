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
        r = redis.Redis(
            host=endpoint,
            port=int(port),
            password=password,
            ssl=True 
        )
        r.ping()
        print("Successfully connected to Upstash Redis.")
        json_data = json.dumps(data, ensure_ascii=False)
        r.set(key_name, json_data)
        print(f"Data successfully pushed to Upstash Redis with key '{key_name}'.")
        
    except redis.exceptions.ConnectionError as e:
        print(f"Redis ConnectionError: Could not connect to Upstash Redis at {endpoint}:{port}. Error: {e}")
        raise 
    except Exception as e:
        print(f"An unexpected error occurred during Redis operation: {e}")
        raise 

def crawl_once():
    UPSTASH_REDIS_ENDPOINT = os.environ.get("UPSTASH_REDIS_ENDPOINT")
    UPSTASH_REDIS_PORT = os.environ.get("UPSTASH_REDIS_PORT")
    UPSTASH_REDIS_PASSWORD = os.environ.get("UPSTASH_REDIS_PASSWORD")
    REDIS_KEY_NAME = "live_election_data" 

    scraped_data = None
    page = None
    browser = None
    screenshot_dir = "playwright-screenshots" 
    os.makedirs(screenshot_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    if not all([UPSTASH_REDIS_ENDPOINT, UPSTASH_REDIS_PORT, UPSTASH_REDIS_PASSWORD]):
        print("Error: Upstash Redis connection details (endpoint, port, password) are not fully configured in environment variables.")
        print(f"Endpoint: {UPSTASH_REDIS_ENDPOINT}, Port: {UPSTASH_REDIS_PORT}, Password Set: {'Yes' if UPSTASH_REDIS_PASSWORD else 'No'}")
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

            target_page_url = "http://info.nec.go.kr/main/showDocument.xhtml?electionId=0020250402&topMenuId=VC&secondMenuId=VCCP09"
            print(f"Step 1: Navigating to target page: {target_page_url}")
            page.goto(target_page_url, wait_until="domcontentloaded", timeout=60_000)
            print("Step 1: Target page navigation completed.")
            
            election_type_selector = "#electionId11"
            sido_dropdown_selector = "select#cityCode"
            search_button_selector = '#spanSubmit input[type="image"][alt="검색"]'

            print(f"Step 2: Clicking on election type tab: '{election_type_selector}'")
            try:
                page.locator(election_type_selector).wait_for(state="visible", timeout=15000)
                page.locator(election_type_selector).click(timeout=10000)
                print("Step 2: Election type tab clicked.")
                
                # "교육감선거" 탭 클릭 후 "시도" 드롭다운과 "검색" 버튼이 모두 나타날 때까지 기다림
                print(f"Waiting for '{sido_dropdown_selector}' and '{search_button_selector}' to be visible after election type click...")
                page.wait_for_selector(sido_dropdown_selector, state="visible", timeout=15000) # 시도 드롭다운 visible 확인
                print(f"'{sido_dropdown_selector}' is now visible.")
                
                # 검색 버튼이 visible 상태인지 확인 (enabled는 click 시 Playwright가 내부적으로 어느정도 체크함)
                page.locator(search_button_selector).wait_for(state="visible", timeout=15000) 
                print(f"'{search_button_selector}' is now visible.")

            except TimeoutError as e:
                print(f"Timeout during Step 2 (election type click or initial element visibility): {e}")
                screenshot_path = os.path.join(screenshot_dir, f"error_step2_timeout_{timestamp}.png")
                if page: page.screenshot(path=screenshot_path, full_page=True)
                raise
            except Exception as e: # Exception을 좀 더 구체적인 Playwright 관련 예외로 바꾸는 것이 좋습니다.
                print(f"Error during Step 2 (election type click or initial element visibility): {e}") # 오류 메시지에 어떤 state를 사용했는지 명시
                screenshot_path = os.path.join(screenshot_dir, f"error_step2_exception_{timestamp}.png")
                if page: page.screenshot(path=screenshot_path, full_page=True)
                raise

            # "시도" 드롭다운에서 "부산광역시" 선택
            print(f"Step 3: Selecting '시도' dropdown (부산광역시) using selector '{sido_dropdown_selector}'...")
            page.select_option(sido_dropdown_selector, "2600") 
            print("Step 3: '시도' (부산광역시) selected.")
            
            # "부산광역시" 선택 후, 페이지가 업데이트될 수 있으므로 검색 버튼을 클릭하기 전에
            # 해당 버튼이 여전히 visible 한지 짧게 확인하거나, 잠시 고정된 시간 대기.
            # 이 단계에서 검색 버튼이 사라지거나 변경되지 않는다는 가정하에 진행.
            # 필요하다면, 여기서도 search_button_selector에 대해 wait_for(state="visible") 재시도.
            print(f"Ensuring search button '{search_button_selector}' is still targetable after '시도' selection...")
            try:
                page.locator(search_button_selector).wait_for(state="visible", timeout=5000) # 짧게 확인
                print("Search button is confirmed to be targetable.")
            except TimeoutError:
                print("Search button not immediately visible after '시도' selection, proceeding with click attempt anyway based on prior visibility.")
                # 스크린샷을 찍고 오류를 발생시킬 수도 있지만, 일단 클릭을 시도해봅니다.
                # page.screenshot(path=os.path.join(screenshot_dir, f"error_search_button_not_visible_final_check_timeout_{timestamp}.png"), full_page=True)
                # raise

            # "검색" 버튼 클릭
            print(f"Step 4: Clicking search button ('{search_button_selector}')...")
            page.locator(search_button_selector).click(timeout=15000) # 클릭 타임아웃 증가
            print("Step 4: Search button clicked.")

            table_selector = "table#table01" 
            print(f"Step 5: Waiting for table ('{table_selector}') to load after search...")
            page.wait_for_selector(table_selector, timeout=60_000)
            print("Step 5: Result table loaded.")

            print(f"Step 6: Extracting HTML from '{table_selector}'...")
            html = page.inner_html(table_selector)
            print("Step 6: HTML extraction completed.")

            print("Step 7: Parsing HTML with BeautifulSoup...")
            soup = BeautifulSoup(html, "lxml")
            
            first_row = soup.select_one("tr")
            if not first_row: raise ValueError("Parsing Error: Could not find the first row in the table HTML.")
            headers = [th.get_text(strip=True) for th in first_row.find_all("th")]
            if not headers: raise ValueError("Parsing Error: Could not parse headers from the table.")

            rows = []
            for tr in soup.select("tr")[1:]:
                cols = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cols: rows.append(cols)
            
            scraped_data = {"headers": headers, "rows": rows}
            print(f"Headers extracted: {headers[:7]}...")
            print(f"Number of data rows extracted: {len(rows)}")
            if rows: print(f"Sample data row: {rows[0][:7]}...")
            print("Step 7: HTML parsing completed.")

        except TimeoutError as e:
            print(f"TimeoutError occurred: {e}")
            if page:
                screenshot_path = os.path.join(screenshot_dir, f"error_timeout_{timestamp}.png")
                try: page.screenshot(path=screenshot_path, full_page=True)
                except Exception as se: print(f"Could not save screenshot: {se}")
            raise 
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            if page:
                screenshot_path = os.path.join(screenshot_dir, f"error_unexpected_{timestamp}.png")
                try: page.screenshot(path=screenshot_path, full_page=True)
                except Exception as se: print(f"Could not save screenshot: {se}")
            raise
        finally:
            if browser:
                print("Closing browser...")
                browser.close()
                print("Browser closed.")

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
            print(f"Error during data push to Upstash Redis: {e}")
            raise
    else:
        print("Skipping Upstash Redis push: No data was scraped.")

if __name__ == "__main__":
    current_timestamp = time.strftime("%Y%m%d-%H%M%S")
    print(f"Starting crawl_once function at {current_timestamp}...")
    crawl_once()
    print(f"crawl_once function finished at {time.strftime('%Y%m%d-%H%M%S')}.")

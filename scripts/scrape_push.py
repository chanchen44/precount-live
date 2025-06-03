import os
import time
import json 
import redis 
from playwright.sync_api import sync_playwright, TimeoutError
from bs4 import BeautifulSoup
import datetime # 타임스탬프용

# --- Upstash Redis로 데이터를 전송하는 함수 ---
def push_to_upstash_redis(data, endpoint, port, password, key_name):
    """
    추출된 데이터를 Upstash Redis에 JSON 문자열로 저장합니다.
    """
    if not data:
        print(f"No data to push to Redis for key '{key_name}'.")
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
        print(f"Successfully connected to Upstash Redis for key '{key_name}'.")
        # datetime 객체가 있다면 문자열로 변환
        json_data = json.dumps(data, ensure_ascii=False, default=str) 
        r.set(key_name, json_data)
        print(f"Data successfully pushed to Upstash Redis with key '{key_name}'.")
        
    except redis.exceptions.ConnectionError as e:
        print(f"Redis ConnectionError for key '{key_name}': Could not connect to Upstash Redis at {endpoint}:{port}. Error: {e}")
        raise 
    except Exception as e:
        print(f"An unexpected error occurred during Redis operation for key '{key_name}': {e}")
        raise 

# --- 최종 결과 계산 함수 ---
def calculate_final_results(scraped_data_from_redis):
    """
    수집된 데이터를 바탕으로 최종 결과를 계산합니다.
    입력: {'timestamp': ..., 'candidates': [...], 'data': [시군구별 상세 데이터], 'summary': {전체 요약}}
    출력: {'timestamp': ..., 
           'total_actual_votes': ..., 
           'projected_votes_by_candidate': {...}, 
           'projected_invalid_votes': ..., 
           'overall_turnout_rate_percent': ...}
    """
    timestamp = scraped_data_from_redis.get("timestamp")
    candidate_names = scraped_data_from_redis.get("candidates")
    sigungu_data_list = scraped_data_from_redis.get("data")
    summary_data = scraped_data_from_redis.get("summary", {}) # 합계 행 데이터

    if not candidate_names or not sigungu_data_list:
        print("Error: Candidate names or sigungu data is missing for calculation.")
        return {"error": "Missing candidate names or data for calculation", "timestamp": timestamp}

    print(f"Calculating final results for candidates: {candidate_names} based on data from {timestamp}")
    
    # 1. 총 투표수 (합계 행에서 가져오기 - 실제 집계된 값)
    total_actual_votes = int(str(summary_data.get("투표수", "0")).replace(',', ''))

    # 2. 후보자별 예상 득표수 및 예상 무효표 계산
    projected_votes_by_candidate = {name: 0.0 for name in candidate_names}
    projected_invalid_votes_total = 0.0 # 예상 무효표 총합
    overall_total_eligible_voters_for_projection = 0 

    for sigungu in sigungu_data_list:
        try:
            sigungu_name = sigungu.get('구시군명', 'N/A')
            eligible_voters_sigungu = int(str(sigungu.get("선거인수", "0")).replace(',', ''))
            votes_cast_sigungu_actual = int(str(sigungu.get("투표수", "0")).replace(',', ''))
            invalid_votes_sigungu_actual = int(str(sigungu.get("무효투표수", "0")).replace(',', '')) # 시군구별 실제 무효표
            
            overall_total_eligible_voters_for_projection += eligible_voters_sigungu

            if votes_cast_sigungu_actual == 0:
                print(f"Warning: Actual votes cast is 0 for {sigungu_name}. Skipping projection for this sigungu.")
                continue

            # 후보자별 예상 득표수 계산
            for cand_name in candidate_names:
                candidate_votes_sigungu_actual = int(str(sigungu.get(cand_name, "0")).replace(',', ''))
                vote_share_in_sigungu = candidate_votes_sigungu_actual / votes_cast_sigungu_actual
                projected_votes_for_candidate_in_sigungu = vote_share_in_sigungu * eligible_voters_sigungu
                projected_votes_by_candidate[cand_name] += projected_votes_for_candidate_in_sigungu
            
            # 시군구별 예상 무효표 계산
            invalid_vote_share_in_sigungu = invalid_votes_sigungu_actual / votes_cast_sigungu_actual
            projected_invalid_votes_sigungu = invalid_vote_share_in_sigungu * eligible_voters_sigungu
            projected_invalid_votes_total += projected_invalid_votes_sigungu
        
        except ValueError as ve:
            print(f"ValueError converting data for sigungu {sigungu_name} during projection: {ve}. Row data: {sigungu}")
            continue 
        except ZeroDivisionError:
            print(f"ZeroDivisionError for sigungu {sigungu_name} (actual votes_cast_sigungu is 0) during projection. Skipping.")
            continue
    
    for cand_name in projected_votes_by_candidate:
        projected_votes_by_candidate[cand_name] = round(projected_votes_by_candidate[cand_name])
    
    projected_invalid_votes_total = round(projected_invalid_votes_total)

    # 3. 개표율 (합계 행에서 가져오기)
    overall_turnout_rate_str = str(summary_data.get("개표율", "0")).replace('%', '').strip()
    overall_turnout_rate = float(overall_turnout_rate_str) if overall_turnout_rate_str else 0.0

    final_results = {
        "timestamp": timestamp,
        "total_actual_votes": total_actual_votes, # 실제 집계된 총 투표수
        "projected_votes_by_candidate": projected_votes_by_candidate,
        "projected_invalid_votes": projected_invalid_votes_total, # 계산된 예상 무효표
        "overall_turnout_rate_percent": overall_turnout_rate, # 실제 집계된 전체 개표율
        "calculation_info": {
            "candidate_projection_method": "Sum_for_each_candidate_over_sigungus_of ((candidate_actual_votes_in_sigungu / total_actual_votes_in_sigungu) * eligible_voters_in_sigungu)",
            "invalid_vote_projection_method": "Sum_over_sigungus_of ((sigungu_actual_invalid_votes / sigungu_total_actual_votes) * sigungu_eligible_voters)",
            "total_eligible_voters_used_for_projection": overall_total_eligible_voters_for_projection,
            "source_overall_actual_votes": summary_data.get("투표수", "N/A"),
            "source_overall_actual_invalid_votes": summary_data.get("무효투표수", "N/A"), # 참고용 실제 집계 무효표
            "source_overall_turnout_rate": summary_data.get("개표율", "N/A")
        }
    }
    print(f"Final calculated results: {final_results}")
    return final_results


def crawl_once():
    UPSTASH_REDIS_ENDPOINT = os.environ.get("UPSTASH_REDIS_ENDPOINT")
    UPSTASH_REDIS_PORT = os.environ.get("UPSTASH_REDIS_PORT")
    UPSTASH_REDIS_PASSWORD = os.environ.get("UPSTASH_REDIS_PASSWORD")
    RAW_DATA_REDIS_KEY = "live_election_data" 
    PROJECTED_DATA_REDIS_KEY = "live_election_data_projected_final"

    scraped_data_for_redis = None 
    page = None
    browser = None
    screenshot_dir = "playwright-screenshots" 
    os.makedirs(screenshot_dir, exist_ok=True)
    current_utc_time = datetime.datetime.now(datetime.timezone.utc)
    execution_timestamp = current_utc_time.isoformat() 
    # 스크린샷 파일명용 타임스탬프 (스크립트 실행 시점 기준)
    file_timestamp = current_utc_time.strftime("%Y%m%d-%H%M%S")


    if not all([UPSTASH_REDIS_ENDPOINT, UPSTASH_REDIS_PORT, UPSTASH_REDIS_PASSWORD]):
        print("Error: Upstash Redis connection details are not fully configured.")
        raise ValueError("Missing Upstash Redis credentials in environment variables.")

    with sync_playwright() as p:
        try:
            print(f"Starting crawl at {execution_timestamp}")
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
                
                print(f"Waiting for '{sido_dropdown_selector}' and '{search_button_selector}' to be ready after election type click...")
                page.wait_for_selector(sido_dropdown_selector, state="visible", timeout=15000)
                print(f"'{sido_dropdown_selector}' is now visible.")
                page.locator(search_button_selector).wait_for(state="visible", timeout=15000)
                print(f"'{search_button_selector}' is now visible.")
            except TimeoutError as e:
                print(f"Timeout during Step 2 (election type click or initial element visibility): {e}")
                screenshot_path = os.path.join(screenshot_dir, f"error_step2_timeout_{file_timestamp}.png")
                if page: page.screenshot(path=screenshot_path, full_page=True)
                raise
            except Exception as e:
                print(f"Error during Step 2 (election type click or initial element visibility): {e}")
                screenshot_path = os.path.join(screenshot_dir, f"error_step2_exception_{file_timestamp}.png")
                if page: page.screenshot(path=screenshot_path, full_page=True)
                raise

            print(f"Step 3: Selecting '시도' dropdown (부산광역시) using selector '{sido_dropdown_selector}'...")
            page.select_option(sido_dropdown_selector, "2600") 
            print("Step 3: '시도' (부산광역시) selected.")
            
            print(f"Waiting for search button '{search_button_selector}' to be ready after '시도' selection...")
            try:
                page.locator(search_button_selector).wait_for(state="visible", timeout=10000) 
                if not page.locator(search_button_selector).is_enabled(timeout=5000):
                    print("Warning: Search button is visible but reported as not enabled shortly after Sido selection. Proceeding with click.")
                print("Search button is confirmed to be targetable.")
            except TimeoutError as e:
                print(f"Timeout waiting for search button to be ready/enabled after '시도' selection: {e}")
                screenshot_path = os.path.join(screenshot_dir, f"error_search_button_not_ready_after_sido_timeout_{file_timestamp}.png")
                if page: page.screenshot(path=screenshot_path, full_page=True)
                raise
            
            print(f"Step 4: Clicking search button ('{search_button_selector}')...")
            page.locator(search_button_selector).click(timeout=15000) 
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
            
            thead = soup.find("thead")
            if not thead: raise ValueError("Parsing Error: Could not find <thead> in the table HTML.")
            header_rows_in_thead = thead.find_all("tr")
            if len(header_rows_in_thead) < 2: raise ValueError("Parsing Error: Expected at least 2 header rows for candidates in <thead>.")

            candidate_names = []
            candidate_header_ths = header_rows_in_thead[1].find_all("th") 
            candidate_th_start_index = 3 
            for th in candidate_header_ths[candidate_th_start_index:]:
                name = th.get_text(strip=True)
                if name == "계": break
                if name: candidate_names.append(name)
            
            if not candidate_names:
                raise ValueError("Critical Parsing Error: Candidate names could not be extracted from table subheader.")
            print(f"Dynamically extracted candidate names: {candidate_names}")
            
            tbody = soup.find("tbody")
            if not tbody: raise ValueError("Parsing Error: Could not find <tbody> in the table HTML.")
            
            sigungu_data_list = []
            summary_row_data = {} 
            data_rows = tbody.find_all("tr")
            
            if not data_rows: raise ValueError("Parsing Error: No data rows found in tbody.")

            for tr_idx, tr in enumerate(data_rows):
                cols_td = tr.find_all("td")
                row_values_text = [td.get_text(strip=True) for td in cols_td]

                if row_values_text and (row_values_text[0] == "합계" or (tr_idx == 0 and "합계" in row_values_text[0])): 
                    print(f"Found summary row: {row_values_text}")
                    summary_row_data["구시군명"] = row_values_text[0]
                    summary_row_data["선거인수"] = row_values_text[1]
                    summary_row_data["투표수"] = row_values_text[2]
                    for i, cand_name in enumerate(candidate_names):
                        summary_row_data[cand_name] = row_values_text[3 + i]
                    
                    summary_idx_offset = 3 + len(candidate_names)
                    if len(row_values_text) > summary_idx_offset:
                        summary_row_data["후보자계"] = row_values_text[summary_idx_offset]
                    if len(row_values_text) > summary_idx_offset + 1:
                        summary_row_data["무효투표수"] = row_values_text[summary_idx_offset + 1]
                    if len(row_values_text) > summary_idx_offset + 2:
                        summary_row_data["기권수"] = row_values_text[summary_idx_offset + 2]
                    if len(row_values_text) > summary_idx_offset + 3: 
                        summary_row_data["개표율"] = row_values_text[summary_idx_offset + 3]
                    continue 

                if not row_values_text or not row_values_text[0] or not row_values_text[1].replace(',','').isdigit():
                    print(f"Skipping likely non-data/percentage row: {row_values_text}")
                    continue
                
                if len(row_values_text) < (3 + len(candidate_names) + 3): # 구시군명,선거인수,투표수 + 후보자수 + 후보자계,무효,기권
                    print(f"Skipping row due to insufficient columns (expected at least {3 + len(candidate_names) + 3}): {row_values_text}")
                    continue

                entry = {}
                entry["구시군명"] = row_values_text[0]
                entry["선거인수"] = row_values_text[1]
                entry["투표수"] = row_values_text[2]
                for i, cand_name in enumerate(candidate_names):
                    entry[cand_name] = row_values_text[3 + i] 
                
                current_idx = 3 + len(candidate_names)
                entry["후보자계"] = row_values_text[current_idx]
                entry["무효투표수"] = row_values_text[current_idx + 1]
                entry["기권수"] = row_values_text[current_idx + 2]
                # 개표율은 시군구별로 없을 수 있으므로, summary에서만 사용
                
                sigungu_data_list.append(entry)

            if not summary_row_data:
                print("Warning: Summary row (합계) not found or parsed. Some overall stats might be inaccurate.")
            if not sigungu_data_list:
                raise ValueError("Parsing Error: No valid sigungu data rows processed after filtering.")

            scraped_data_for_redis = {
                "timestamp": execution_timestamp, 
                "candidates": candidate_names, 
                "data": sigungu_data_list,
                "summary": summary_row_data
            }
            print(f"Data prepared for Redis (timestamp: {execution_timestamp})")
            print(f"Candidate names for Redis: {candidate_names}")
            print(f"Number of sigungu data rows for Redis: {len(sigungu_data_list)}")
            if sigungu_data_list: print(f"Sample sigungu data entry for Redis: {sigungu_data_list[0]}")
            if summary_row_data: print(f"Summary row data for Redis: {summary_row_data}")
            print("Step 7: HTML parsing completed.")

        except TimeoutError as e:
            print(f"TimeoutError occurred: {e}")
            if page:
                screenshot_path = os.path.join(screenshot_dir, f"error_timeout_{file_timestamp}.png")
                try: page.screenshot(path=screenshot_path, full_page=True)
                except Exception as se: print(f"Could not save screenshot: {se}")
            raise 
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            if page:
                screenshot_path = os.path.join(screenshot_dir, f"error_unexpected_{file_timestamp}.png")
                try: page.screenshot(path=screenshot_path, full_page=True)
                except Exception as se: print(f"Could not save screenshot: {se}")
            raise
        finally:
            if browser:
                print("Closing browser...")
                browser.close()
                print("Browser closed.")

    if scraped_data_for_redis:
        print(f"Step 8: Attempting to push RAW data to Upstash Redis with key '{RAW_DATA_REDIS_KEY}'...")
        try:
            push_to_upstash_redis(
                scraped_data_for_redis, 
                UPSTASH_REDIS_ENDPOINT, 
                UPSTASH_REDIS_PORT, 
                UPSTASH_REDIS_PASSWORD,
                RAW_DATA_REDIS_KEY
            )
            print("Step 8: RAW data push to Upstash Redis finished.")

            print("Step 9: Calculating final results...")
            calculated_results = calculate_final_results(scraped_data_for_redis)
            if calculated_results and "error" not in calculated_results :
                print(f"Step 9.5: Attempting to push FINAL calculated data to Upstash Redis with key '{PROJECTED_DATA_REDIS_KEY}'...")
                push_to_upstash_redis(
                    calculated_results,
                    UPSTASH_REDIS_ENDPOINT,
                    UPSTASH_REDIS_PORT,
                    UPSTASH_REDIS_PASSWORD,
                    PROJECTED_DATA_REDIS_KEY
                )
                print("Step 9.5: FINAL calculated data push to Upstash Redis finished.")
            else:
                error_msg = calculated_results.get('error', 'Unknown calculation error') if isinstance(calculated_results, dict) else "Calculation function returned None or unexpected type"
                print(f"Step 9: Could not calculate final results or an error occurred: {error_msg}")
        except Exception as e:
            print(f"Error during data push or calculation: {e}")
            raise
    else:
        print("Skipping Upstash Redis push and calculation: No data was scraped.")

if __name__ == "__main__":
    script_start_time = time.strftime("%Y%m%d-%H%M%S")
    print(f"Starting crawl_once function at {script_start_time}...")
    crawl_once()
    print(f"crawl_once function finished at {time.strftime('%Y%m%d-%H%M%S')}.")

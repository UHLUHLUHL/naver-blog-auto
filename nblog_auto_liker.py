import gradio as gr
import time
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# --- 셀레니움 봇 클래스 ---
class NaverBlogBot:
    """
    Selenium을 사용하여 네이버 블로그 자동화 작업을 수행하는 클래스.
    """
    def __init__(self):
        self.driver = None
        self.stop_event = threading.Event()

    def _initialize_driver(self):
        """WebDriver를 초기화합니다."""
        try:
            options = webdriver.ChromeOptions()
            # options.add_argument("--headless")  # UI 없이 실행하려면 이 옵션 활성화
            options.add_argument("--disable-gpu")
            options.add_argument("--log-level=3") # 콘솔 로그 최소화
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36")
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.implicitly_wait(5) # 암시적 대기 설정
            return True
        except Exception as e:
            self.log(f"드라이버 초기화 실패: {e}", "ERROR")
            return False

    def log(self, message, log_type="INFO"):
        """Gradio UI에 표시될 로그 메시지를 생성합니다."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"[{timestamp}][{log_type}] {message}\n"

    def stop(self):
        """봇의 작동 중지를 요청합니다."""
        self.stop_event.set()

    def _login(self, naver_id, naver_pw):
        """네이버 로그인을 수행합니다."""
        self.driver.get('https://nid.naver.com/nidlogin.login')
        yield self.log("로그인 페이지로 이동했습니다.")
        
        # IP 보안 해제
        try:
            # 'IP보안' 텍스트를 포함하는 label을 찾아 클릭
            ip_security_label = self.driver.find_element(By.XPATH, "//label[contains(., 'IP보안')]")
            ip_security_label.click()
            # smart_LEVEL 값을 직접 변경하는 것은 안정적이지 않으므로, UI 클릭으로 처리
            yield self.log("IP 보안 기능을 OFF로 설정했습니다.")
        except NoSuchElementException:
            yield self.log("IP 보안 설정 버튼을 찾을 수 없습니다. 계속 진행합니다.", "WARN")
        except Exception as e:
            yield self.log(f"IP 보안 설정 중 오류 발생: {e}", "ERROR")

        time.sleep(1)

        # 자바스크립트를 이용해 아이디와 비밀번호 입력 (봇 탐지 우회)
        self.driver.execute_script(f"document.getElementById('id').value = '{naver_id}'")
        self.driver.execute_script(f"document.getElementById('pw').value = '{naver_pw}'")
        yield self.log("ID와 비밀번호를 입력했습니다.")
        
        # 로그인 버튼 클릭
        self.driver.find_element(By.ID, 'log.login').click()
        
        # 로그인 성공/실패 확인
        try:
            # 2FA (2단계 인증) 또는 새 기기 등록 페이지 확인
            WebDriverWait(self.driver, 5).until(
                EC.any_of(
                    EC.presence_of_element_located((By.ID, "my_info")), # 로그인 성공 시 '내 정보'
                    EC.presence_of_element_located((By.ID, "new.save")), # 새 기기 등록
                    EC.presence_of_element_located((By.ID, "err_common")) # 로그인 실패
                )
            )

            current_url = self.driver.current_url
            if "nid.naver.com/login/sso/finalize" in current_url or "www.naver.com" in current_url:
                 yield self.log("로그인에 성공했습니다!")
                 return True
            elif "nid.naver.com/login/ext/deviceConfirm" in current_url:
                 yield self.log("새로운 기기 등록이 필요합니다. 브라우저에서 직접 등록 후 다시 시도해주세요.", "WARN")
                 # 사용자가 직접 처리할 수 있도록 30초 대기
                 time.sleep(30)
                 return True # 일단 성공으로 간주하고 다음 단계로 진행
            else:
                 error_element = self.driver.find_element(By.ID, "err_common")
                 yield self.log(f"로그인 실패: {error_element.text}", "ERROR")
                 return False

        except TimeoutException:
            # 페이지 URL로 성공 여부 재확인
            if "www.naver.com" in self.driver.current_url:
                 yield self.log("로그인에 성공했습니다! (URL 확인)")
                 return True
            else:
                yield self.log("로그인 페이지에서 벗어나지 못했습니다. ID/PW를 확인해주세요.", "ERROR")
                return False

    def _like_posts(self):
        """이웃 새글 페이지를 순회하며 '공감'을 누릅니다."""
        current_page = 1
        total_liked_count = 0
        yield self.log("이웃 새글 공감 작업을 시작합니다.")

        while True:
            if self.stop_event.is_set():
                yield self.log("사용자에 의해 작업이 중지되었습니다.", "WARN")
                break
            
            # 페이지 URL 구성 및 이동
            target_url = f"https://section.blog.naver.com/BlogHome.naver?directoryNo=0&currentPage={current_page}&groupId=0"
            self.driver.get(target_url)
            yield self.log(f"이웃 새글 {current_page}페이지로 이동했습니다.")
            time.sleep(2.5) # 페이지 로딩 대기

            # 공감하지 않은 글의 '공감' 버튼 찾기 (수정된 CSS 선택자)
            # class에 'off'가 있고, aria-pressed가 'false'인 버튼을 찾습니다.
            like_buttons_to_click = self.driver.find_elements(By.CSS_SELECTOR, "a.u_likeit_list_btn.off[aria-pressed='false']")

            # 더 이상 공감할 글이 없으면 작업 종료
            if not like_buttons_to_click:
                yield self.log("현재 페이지에서 공감할 새 글을 찾지 못했습니다. 작업을 종료합니다.", "INFO")
                break

            page_liked_count = 0
            for button in like_buttons_to_click:
                if self.stop_event.is_set():
                    break
                try:
                    # 자바스크립트로 클릭하여 ElementClickInterceptedException 방지
                    self.driver.execute_script("arguments[0].click();", button)
                    page_liked_count += 1
                    total_liked_count += 1
                    yield self.log(f"└ 포스트에 공감했습니다! (현재 페이지: {page_liked_count}개, 총: {total_liked_count}개)", "SUCCESS")
                    time.sleep(1.5) # 네이버 서버 부하를 줄이기 위한 딜레이
                except Exception as e:
                    yield self.log(f"└ 공감 버튼 클릭 중 오류가 발생했습니다: {e}", "ERROR")
            
            yield self.log(f"{current_page}페이지에서 총 {page_liked_count}개의 포스트에 공감했습니다.")
            
            # 다음 페이지로 이동
            current_page += 1

        yield self.log(f"작업 완료! 총 {total_liked_count}개의 포스트에 공감했습니다.", "SUCCESS")


    def run(self, naver_id, naver_pw):
        """자동화 봇의 전체 실행 로직을 담당합니다."""
        self.stop_event.clear()
        
        if not self._initialize_driver():
            yield self.log("봇을 시작할 수 없습니다. 프로그램을 종료합니다.", "ERROR")
            return

        # 로그인 시도
        login_generator = self._login(naver_id, naver_pw)
        login_success = False
        for log_msg in login_generator:
            yield log_msg
            if "로그인에 성공" in log_msg:
                login_success = True
        
        if not login_success:
            yield self.log("로그인에 실패하여 작업을 중단합니다.", "ERROR")
            self.driver.quit()
            return

        # '공감' 작업 수행
        like_generator = self._like_posts()
        for log_msg in like_generator:
            yield log_msg
            if self.stop_event.is_set():
                break
        
        yield self.log("자동 좋아요 작업을 완료했습니다.", "INFO")
        self.driver.quit()
        self.driver = None


# --- Gradio UI 및 이벤트 핸들러 ---
bot_instance = NaverBlogBot()

def start_bot_process(naver_id, naver_pw):
    """'Start' 버튼 클릭 시 봇 실행을 시작하는 제너레이터 함수."""
    if not naver_id or not naver_pw:
        yield bot_instance.log("ID와 비밀번호를 모두 입력해주세요.", "ERROR"), "IDLE"
        return

    # 봇 실행 제너레이터를 통해 로그를 실시간으로 받아옴
    log_output = ""
    yield " ", "RUNNING" # 로그 초기화 및 상태 변경
    
    for log_message in bot_instance.run(naver_id, naver_pw):
        log_output += log_message
        yield log_output, "RUNNING"
    
    yield log_output, "FINISHED"


def stop_bot_process():
    """'Stop' 버튼 클릭 시 봇을 중지시킵니다."""
    bot_instance.stop()
    return "STOPPED"

# Gradio UI 구성
# gr.themes.Base()는 기본적으로 다크 모드를 지원합니다.
with gr.Blocks(theme=gr.themes.Base(primary_hue=gr.themes.colors.green, secondary_hue=gr.themes.colors.blue), title="Naver Blog Auto-Liker") as app:
    bot_state = gr.State("IDLE")

    with gr.Row():
        gr.HTML("""
            <div style="display: flex; align-items: center; justify-content: center; gap: 12px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-heart-handshake"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/><path d="M12 5 9.04 7.96a2.17 2.17 0 0 0 0 3.08v0c.82.82 2.13.82 2.94 0l.06-.06L12 11l2.96-2.96c.82-.82 2.13-.82 2.94 0l0 0a2.17 2.17 0 0 0 0-3.08L12 5Z"/></svg>
                <h1 style="font-size: 2em; font-weight: 700;">Naver Blog Auto-Liker</h1>
            </div>
        """)

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("## ⚙️ 제어판 (Control Panel)")
            naver_id_input = gr.Textbox(label="네이버 ID", placeholder="아이디를 입력하세요")
            naver_pw_input = gr.Textbox(label="네이버 비밀번호", type="password", placeholder="비밀번호를 입력하세요")
            
            with gr.Row():
                start_button = gr.Button("🤖 봇 시작", variant="primary")
                stop_button = gr.Button("🛑 봇 중지")

            gr.Markdown("### 📊 현재 상태 (Bot Status)")
            status_output = gr.Textbox(value="IDLE", label="상태", interactive=False)
            
        with gr.Column(scale=2):
            gr.Markdown("## 📝 상태 로그 (Status Log)")
            log_output = gr.Textbox(
                label="실시간 로그",
                lines=20,
                interactive=False,
                autoscroll=True,
                max_lines=20
            )

    # 이벤트 핸들러 연결
    start_event = start_button.click(
        fn=start_bot_process,
        inputs=[naver_id_input, naver_pw_input],
        outputs=[log_output, status_output]
    )
    
    stop_button.click(
        fn=stop_bot_process,
        inputs=None,
        outputs=[status_output],
        cancels=[start_event] # 시작 이벤트 취소
    )

if __name__ == "__main__":
    # 최신 Gradio 버전에서는 launch() 함수에 'dark' 인자가 없습니다.
    # 테마 자체에서 다크 모드를 설정해야 합니다.
    app.launch()

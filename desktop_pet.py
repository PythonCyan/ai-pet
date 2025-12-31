import pygame
import sys
import random
import os
import platform
import threading
import json
import urllib.request
import urllib.error
import base64
from PIL import ImageGrab, Image

# 尝试引入 SDL2 Window 对象 (需要安装 pygame-ce)
try:
    from pygame._sdl2.video import Window
except ImportError:
    Window = None
    print("建议安装 pygame-ce 以获得最佳体验: pip uninstall pygame && pip install pygame-ce")

# --- 配置常量 ---
WIDGET_WIDTH = 340
STATUS_BAR_HEIGHT = 30  # 状态栏高度
FACE_HEIGHT = 140  # 眼睛区域高度
CHAT_PANEL_HEIGHT = 420  # 聊天区域高度
MINI_SIZE = 90  # 浮球模式的大小

# 颜色配置
BODY_BG_COLOR = (15, 15, 20)  # 身体背景色
STATUS_BG_COLOR = (0, 0, 0, 80)  # 状态栏背景
MINI_BG_COLOR = (0, 0, 0, 150)  # 浮球背景

EYE_COLOR = (0, 255, 255)
USER_COLOR = (0, 200, 255)
BOT_COLOR = (50, 255, 100)
TEXT_COLOR = (220, 220, 220)
STATUS_TEXT_COLOR = (200, 200, 200)

FONT_SIZE = 16
STATUS_FONT_SIZE = 12

# 状态常量
STATE_IDLE = "idle"
STATE_CHAT = "chat"
STATE_MINI = "mini"

EMOTION_NORMAL = "normal"
EMOTION_HAPPY = "happy"
EMOTION_ANGRY = "angry"
EMOTION_THINKING = "thinking"


class DesktopPetWidget:
    def __init__(self):
        pygame.init()
        pygame.key.start_text_input()

        self.load_config()

        self.state = STATE_IDLE
        self.emotion = EMOTION_NORMAL

        # 初始尺寸
        self.current_w = WIDGET_WIDTH
        self.current_h = STATUS_BAR_HEIGHT + FACE_HEIGHT

        # 状态数据
        self.level = 3
        self.health = 100
        self.status_icon = ""

        # 初始化屏幕
        self.screen = pygame.display.set_mode(
            (self.current_w, self.current_h),
            pygame.NOFRAME | pygame.SRCALPHA
        )
        self.clock = pygame.time.Clock()

        # [新增] 窗口控制与置顶状态
        self.window_obj = None
        self.is_pinned = True  # 默认开启置顶
        self.init_window_control()
        self.set_initial_position()

        # 字体
        self.font = self.load_chinese_font(FONT_SIZE)
        self.status_font = self.load_chinese_font(STATUS_FONT_SIZE)

        # 交互数据
        self.dragging = False
        self.drag_offset = (0, 0)
        self.blink_timer = 0
        self.is_blinking = False

        self.user_input = ""
        self.chat_history = []
        self.cursor_blink = 0

        self.ai_response_buffer = ""
        self.is_typing = False
        self.last_type_time = 0

        self.pending_image_path = None
        self.pending_image_surf = None

        # 按钮区域
        self.minimize_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.pin_btn_rect = pygame.Rect(0, 0, 0, 0)  # [新增] 置顶按钮区域

        self.add_to_history("System", "Ready.")

    # --- 核心状态切换逻辑 ---

    def switch_state(self, new_state):
        if self.state == new_state: return

        self.state = new_state
        old_center = None

        # 记录切换前的中心点
        if self.window_obj:
            try:
                x, y = self.window_obj.position
                old_center = (x + self.current_w // 2, y + self.current_h // 2)
            except:
                pass

        # 根据新状态设定尺寸
        if new_state == STATE_MINI:
            self.current_w = MINI_SIZE
            self.current_h = MINI_SIZE
        elif new_state == STATE_IDLE:
            self.current_w = WIDGET_WIDTH
            self.current_h = STATUS_BAR_HEIGHT + FACE_HEIGHT
            self.user_input = ""
        elif new_state == STATE_CHAT:
            self.current_w = WIDGET_WIDTH
            self.current_h = STATUS_BAR_HEIGHT + FACE_HEIGHT + CHAT_PANEL_HEIGHT

        # 重建窗口
        self.screen = pygame.display.set_mode(
            (self.current_w, self.current_h),
            pygame.NOFRAME | pygame.SRCALPHA
        )
        self.init_window_control()

        # 恢复中心位置
        if old_center and self.window_obj:
            new_x = int(old_center[0] - self.current_w / 2)
            new_y = int(old_center[1] - self.current_h / 2)
            self.window_obj.position = (new_x, new_y)

    # --- 基础工具 ---

    def add_to_history(self, role, text):
        self.chat_history.append({"role": role, "text": text})
        if len(self.chat_history) > 50: self.chat_history.pop(0)

    def handle_image_ready(self, surf, path):
        self.pending_image_path = path
        w, h = surf.get_size()
        scale = 50 / h
        self.pending_image_surf = pygame.transform.scale(surf, (int(w * scale), 50))
        if self.state != STATE_CHAT:
            self.switch_state(STATE_CHAT)

    def set_initial_position(self):
        if self.window_obj:
            try:
                screen_w, screen_h = pygame.display.get_desktop_sizes()[0]
                pos_x = (screen_w - self.current_w) // 2
                self.window_obj.position = (pos_x, 100)
            except:
                pass

    def load_config(self):
        try:
            with open("config.json", "r", encoding='utf-8') as f:
                self.config = json.load(f)
        except:
            self.config = {"api_key": "", "api_url": "", "model": "qwen-vl-plus"}

    def load_chinese_font(self, size):
        system = platform.system()
        if system == 'Darwin':
            fonts = ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"]
            for p in fonts:
                if os.path.exists(p): return pygame.font.Font(p, size)
        elif system == 'Windows':
            fonts = ["C:\\Windows\\Fonts\\msyh.ttc", "C:\\Windows\\Fonts\\simhei.ttf"]
            for p in fonts:
                if os.path.exists(p): return pygame.font.Font(p, size)
        if os.path.exists("font.ttf"): return pygame.font.Font("font.ttf", size)
        return pygame.font.SysFont("Arial", size)

    def init_window_control(self):
        if Window:
            try:
                self.window_obj = Window.from_display_module()
                # [修改] 使用 self.is_pinned 变量来决定初始置顶状态
                self.window_obj.always_on_top = self.is_pinned
                self.window_obj.opacity = 1.0
            except:
                pass

    def wrap_text_dynamic(self, text, max_width):
        lines = []
        if not text: return lines
        curr = ""
        for char in text:
            if self.font.size(curr + char)[0] < max_width:
                curr += char
            else:
                lines.append(curr)
                curr = char
        if curr: lines.append(curr)
        return lines

    def filter_unsupported_chars(self, text):
        return "".join([c if ord(c) < 0x10000 else " " for c in text])

    def update_typewriter(self):
        if self.is_typing and self.ai_response_buffer:
            if pygame.time.get_ticks() - self.last_type_time > 30:
                c = self.ai_response_buffer[0]
                self.ai_response_buffer = self.ai_response_buffer[1:]
                if self.chat_history and self.chat_history[-1]["role"] == "Bot":
                    self.chat_history[-1]["text"] += c
                else:
                    self.chat_history.append({"role": "Bot", "text": c})
                self.last_type_time = pygame.time.get_ticks()
                if not self.ai_response_buffer:
                    self.is_typing = False
                    self.emotion = EMOTION_NORMAL
                    self.status_icon = ""

    def analyze_emotion(self, text):
        t = text.lower()
        self.status_icon = ""
        if any(k in t for k in ["哈哈", "开心", "成功"]):
            self.emotion = EMOTION_HAPPY
            self.health = min(100, self.health + 1)
        elif any(k in t for k in ["错误", "error", "失败"]):
            self.emotion = EMOTION_ANGRY
            self.status_icon = "!"
            self.health = max(0, self.health - 2)
        elif any(k in t for k in ["思考", "thinking"]):
            self.emotion = EMOTION_THINKING
            self.status_icon = "?"
        else:
            self.emotion = EMOTION_NORMAL

    # --- 绘图逻辑 ---

    def draw_eyes(self, surface, center_y, scale=1.0):
        mx, my = pygame.mouse.get_pos()
        if self.state == STATE_MINI and self.window_obj:
            wx, wy = self.window_obj.position
            mx = mx - wx
            my = my - wy

        lx, rx = self.current_w // 3, self.current_w * 2 // 3
        ox = max(-8, min(8, (mx - self.current_w / 2) / 15))
        oy = max(-8, min(8, (my - center_y) / 15))

        self.blink_timer -= 1
        if self.blink_timer <= 0:
            self.is_blinking = not self.is_blinking
            self.blink_timer = 5 if self.is_blinking else random.randint(150, 400)

        c = EYE_COLOR
        if self.emotion == EMOTION_ANGRY:
            c = (255, 50, 50)
        elif self.emotion == EMOTION_THINKING:
            c = (255, 200, 0)
        elif self.emotion == EMOTION_HAPPY:
            c = (50, 255, 100)

        eye_w, eye_h = 30 * scale, 40 * scale

        if self.is_blinking:
            pygame.draw.rect(surface, c, (lx - eye_w / 2, center_y + oy, eye_w, 4 * scale))
            pygame.draw.rect(surface, c, (rx - eye_w / 2, center_y + oy, eye_w, 4 * scale))
        else:
            if self.emotion == EMOTION_HAPPY:
                pygame.draw.arc(surface, c, (lx - eye_w / 2 + ox, center_y - 10 * scale + oy, eye_w, 20 * scale), 0,
                                3.14, 3)
                pygame.draw.arc(surface, c, (rx - eye_w / 2 + ox, center_y - 10 * scale + oy, eye_w, 20 * scale), 0,
                                3.14, 3)
            else:
                pygame.draw.ellipse(surface, c, (lx - eye_w / 2 + ox, center_y - 20 * scale + oy, eye_w, eye_h))
                pygame.draw.ellipse(surface, c, (rx - eye_w / 2 + ox, center_y - 20 * scale + oy, eye_w, eye_h))

    def draw_normal_window(self):
        # 1. 绘制不透明的身体部分
        body_rect = pygame.Rect(0, STATUS_BAR_HEIGHT, self.current_w, self.current_h - STATUS_BAR_HEIGHT)
        pygame.draw.rect(self.screen, BODY_BG_COLOR, body_rect)
        pygame.draw.rect(self.screen, (60, 60, 70), body_rect, 1)

        # 2. 绘制半透明状态栏
        status_rect = pygame.Rect(0, 0, self.current_w, STATUS_BAR_HEIGHT)
        status_surf = pygame.Surface((self.current_w, STATUS_BAR_HEIGHT), pygame.SRCALPHA)
        status_surf.fill(STATUS_BG_COLOR)

        # 状态文字
        mood_txt = {EMOTION_NORMAL: "Data", EMOTION_HAPPY: "Happy", EMOTION_ANGRY: "Angry",
                    EMOTION_THINKING: "Thinking"}.get(self.emotion, "Data")
        status_surf.blit(self.status_font.render(f"LV.{self.level}", True, STATUS_TEXT_COLOR), (10, 8))
        status_surf.blit(
            self.status_font.render(f"HP: {self.health}%", True,
                                    (50, 255, 100) if self.health > 30 else (255, 50, 50)),
            (60, 8))
        status_surf.blit(self.status_font.render(f"Mood: {mood_txt}", True, STATUS_TEXT_COLOR), (140, 8))

        # 最小化按钮 [-]
        btn_x = self.current_w - 30
        self.minimize_btn_rect = pygame.Rect(btn_x, 0, 30, STATUS_BAR_HEIGHT)
        pygame.draw.line(status_surf, STATUS_TEXT_COLOR, (btn_x + 8, 15), (btn_x + 22, 15), 2)

        # [新增] 置顶按钮 [📌]
        # 在最小化按钮左侧 30 像素
        pin_x = btn_x - 30
        self.pin_btn_rect = pygame.Rect(pin_x, 0, 30, STATUS_BAR_HEIGHT)
        pin_center = (pin_x + 15, 15)

        # 颜色逻辑：开启=亮绿，关闭=暗灰
        pin_color = (0, 255, 100) if self.is_pinned else (100, 100, 100)

        if self.is_pinned:
            # 实心圆 (表示已钉住)
            pygame.draw.circle(status_surf, pin_color, pin_center, 5)
        else:
            # 空心圆 (表示未钉住)
            pygame.draw.circle(status_surf, pin_color, pin_center, 5, 1)

        # 特殊状态图标
        if self.status_icon:
            ico = self.font.render(self.status_icon, True, (255, 255, 0))
            status_surf.blit(ico, (self.current_w - 80, 2)) # 稍微往左挪一点避免挡住按钮

        self.screen.blit(status_surf, (0, 0))
        pygame.draw.line(self.screen, (50, 50, 60), (0, STATUS_BAR_HEIGHT), (self.current_w, STATUS_BAR_HEIGHT), 1)

        # 3. 绘制眼睛
        self.draw_eyes(self.screen, STATUS_BAR_HEIGHT + FACE_HEIGHT // 2)

        # 4. 绘制聊天面板
        if self.state == STATE_CHAT:
            chat_y = STATUS_BAR_HEIGHT + FACE_HEIGHT
            pygame.draw.line(self.screen, (50, 50, 50), (10, chat_y), (self.current_w - 10, chat_y), 1)

            input_h = 50 + (60 if self.pending_image_surf else 0)
            hist_h = CHAT_PANEL_HEIGHT - input_h - 10

            lines = []
            for m in self.chat_history:
                col = USER_COLOR if m["role"] == "User" else BOT_COLOR
                if m["role"] == "System": col = (100, 100, 100)
                raw = f"{m['role']}: {self.filter_unsupported_chars(m['text'])}"
                for l in self.wrap_text_dynamic(raw, self.current_w - 30): lines.append((l, col))

            vis = lines[-(hist_h // (FONT_SIZE + 6)):] if len(lines) > 0 else []
            cy = chat_y + 10
            for t, c in vis:
                self.screen.blit(self.font.render(t, True, c), (15, cy))
                cy += FONT_SIZE + 6

            iy = self.current_h - input_h
            pygame.draw.line(self.screen, (40, 40, 45), (0, iy), (self.current_w, iy))
            if self.pending_image_surf:
                self.screen.blit(self.pending_image_surf, (15, iy + 5))
                iy += 60

            cursor = "_" if (self.cursor_blink // 30) % 2 == 0 else ""
            self.cursor_blink += 1
            prompt = f"> {self.filter_unsupported_chars(self.user_input)}{cursor}"
            self.screen.blit(self.font.render(prompt, True, TEXT_COLOR), (15, iy + 15))
            try:
                pygame.key.set_text_input_rect(pygame.Rect(15, iy + 30, 200, 50))
            except:
                pass

    def draw_mini_ball(self):
        center = (MINI_SIZE // 2, MINI_SIZE // 2)
        radius = MINI_SIZE // 2 - 2
        pygame.draw.circle(self.screen, MINI_BG_COLOR, center, radius)
        pygame.draw.circle(self.screen, EYE_COLOR, center, radius, 2)
        self.draw_eyes(self.screen, center[1], scale=0.6)

    def draw(self):
        self.screen.fill((0, 0, 0, 0))
        if self.state == STATE_MINI:
            self.draw_mini_ball()
        else:
            self.draw_normal_window()

    # --- 线程 ---
    def call_api_thread(self, prompt, image_path):
        try:
            msgs = [{"role": "system", "content": self.config.get("system_prompt", "")}]
            if image_path:
                with open(image_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                msgs.append({"role": "user", "content": [{"type": "text", "text": prompt or "图里有什么"},
                                                         {"type": "image_url",
                                                          "image_url": {"url": f"data:image/png;base64,{b64}"}}]})
            else:
                msgs.append({"role": "user", "content": prompt})

            self.emotion = EMOTION_THINKING
            self.status_icon = "?"

            req = urllib.request.Request(
                self.config.get("api_url"),
                data=json.dumps({"model": self.config.get("model"), "messages": msgs}).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.config.get('api_key')}"}
            )
            with urllib.request.urlopen(req) as res:
                js = json.loads(res.read().decode())
                reply = js['choices'][0]['message']['content']
                self.analyze_emotion(reply)
                self.ai_response_buffer = reply
                self.is_typing = True
                self.chat_history.append({"role": "Bot", "text": ""})
                self.level += 1
        except Exception as e:
            self.add_to_history("Sys", f"Err: {e}")
            self.emotion = EMOTION_ANGRY
            self.status_icon = "!"
        if image_path and "temp" in image_path:
            try:
                os.remove(image_path)
            except:
                pass

    def handle_paste(self):
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                path = os.path.join(os.getcwd(), "temp_clipboard.png")
                img.save(path)
                mode, size, data = img.mode, img.size, img.tobytes()
                py_img = pygame.image.fromstring(data, size, mode)
                self.handle_image_ready(py_img, path)
                return
        except:
            pass
        t = pygame.scrap.get(pygame.SCRAP_TEXT)
        if t: self.user_input += t.decode('utf-8').strip('\x00')

    def run(self):
        running = True
        pygame.scrap.init()
        last_click_time = 0

        while running:
            self.update_typewriter()
            events = pygame.event.get()

            for event in events:
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.state == STATE_MINI:
                            now = pygame.time.get_ticks()
                            if now - last_click_time < 500:
                                self.switch_state(STATE_IDLE)
                                last_click_time = 0
                            else:
                                last_click_time = now
                                self.dragging = True
                                self.drag_offset = event.pos
                        else:
                            # 1. 检测最小化
                            if self.minimize_btn_rect.collidepoint(event.pos):
                                self.switch_state(STATE_MINI)

                            # 2. [新增] 检测置顶按钮点击
                            elif self.pin_btn_rect.collidepoint(event.pos):
                                self.is_pinned = not self.is_pinned
                                if self.window_obj:
                                    self.window_obj.always_on_top = self.is_pinned

                            # 3. 拖动区域
                            elif event.pos[1] < (STATUS_BAR_HEIGHT + FACE_HEIGHT):
                                self.dragging = True
                                self.drag_offset = event.pos

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1: self.dragging = False

                elif event.type == pygame.MOUSEMOTION:
                    if self.dragging and self.window_obj:
                        mx, my = event.pos
                        dx = mx - self.drag_offset[0]
                        dy = my - self.drag_offset[1]
                        wx, wy = self.window_obj.position
                        self.window_obj.position = (wx + dx, wy + dy)

                elif event.type == pygame.DROPFILE:
                    if os.path.exists(event.file):
                        try:
                            img = pygame.image.load(event.file)
                            self.handle_image_ready(img, event.file)
                        except:
                            pass

                elif event.type == pygame.KEYDOWN:
                    is_ctrl = (event.mod & pygame.KMOD_CTRL) or (event.mod & pygame.KMOD_META)

                    if self.state != STATE_MINI:
                        if event.key == pygame.K_SPACE and self.state == STATE_IDLE:
                            self.switch_state(STATE_CHAT)
                        elif event.key == pygame.K_ESCAPE:
                            if self.state == STATE_CHAT:
                                self.switch_state(STATE_IDLE)
                            else:
                                running = False

                        if self.state == STATE_CHAT:
                            if event.key == pygame.K_v and is_ctrl:
                                self.handle_paste()
                            elif event.key == pygame.K_RETURN:
                                if self.user_input.strip() or self.pending_image_path:
                                    t, i = self.user_input, self.pending_image_path
                                    self.add_to_history("User", t + (" [IMG]" if i else ""))
                                    self.user_input = ""
                                    self.pending_image_path = None
                                    self.pending_image_surf = None
                                    threading.Thread(target=self.call_api_thread, args=(t, i)).start()
                            elif event.key == pygame.K_BACKSPACE:
                                self.user_input = self.user_input[:-1]

                elif event.type == pygame.TEXTINPUT and self.state == STATE_CHAT:
                    self.user_input += event.text

            self.draw()
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    DesktopPetWidget().run()
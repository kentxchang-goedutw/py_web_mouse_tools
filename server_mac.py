#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macOS 版虛擬滑鼠伺服器
用法: python server_mac.py
首次使用需在「系統設定 > 隱私權與安全性 > 輔助使用」允許權限
"""

import tkinter as tk
from tkinter import ttk
import qrcode
from PIL import Image, ImageTk
import socket
import threading
import os
import sys
import json
import platform

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import pyautogui

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

IS_MAC = platform.system() == 'Darwin'

_mouse_held = set()

if IS_MAC:
    try:
        from Quartz import (
            CGEventCreate, CGEventGetLocation,
            CGEventCreateMouseEvent, CGEventPost,
            kCGEventLeftMouseDown, kCGEventLeftMouseUp,
            kCGEventLeftMouseDragged, kCGEventMouseMoved,
            kCGEventRightMouseDown, kCGEventRightMouseUp,
            kCGEventRightMouseDragged,
            kCGMouseButtonLeft, kCGMouseButtonRight,
            kCGHIDEventTap,
        )
        HAS_QUARTZ = True
    except ImportError:
        HAS_QUARTZ = False
else:
    HAS_QUARTZ = False


def _mac_mouse_pos():
    evt = CGEventCreate(None)
    loc = CGEventGetLocation(evt)
    return loc.x, loc.y


def _mac_send(event_type, x, y, button=kCGMouseButtonLeft):
    evt = CGEventCreateMouseEvent(None, event_type, (x, y), button)
    CGEventPost(kCGHIDEventTap, evt)


if getattr(sys, 'frozen', False):
    APP_DIR = sys._MEIPASS
    DATA_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = APP_DIR

TEMPLATE_DIR = os.path.join(APP_DIR, 'templates')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

FONT_FAMILY = 'PingFang TC' if IS_MAC else 'Microsoft JhengHei'

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'password': ''}

def save_config(pw):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({'password': pw}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.config['SECRET_KEY'] = 'virtual-mouse-secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

password = ""
authenticated_clients = set()
SERVER_STARTED = False

pyautogui.FAILSAFE = False

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def generate_qr_img(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

@app.route('/')
def index():
    return render_template('index.html', has_password=bool(password))

@app.route('/check_password', methods=['POST'])
def check_password():
    global password
    data = request.get_json(silent=True) or {}
    if password and data.get('password') != password:
        return {'success': False, 'message': 'Wrong password'}
    return {'success': True}

@socketio.on('connect')
def handle_connect():
    if not password:
        authenticated_clients.add(request.sid)
        emit('auth_ok')

@socketio.on('auth')
def handle_auth(data):
    global password
    pwd = data.get('password', '')
    if not password or pwd == password:
        authenticated_clients.add(request.sid)
        emit('auth_ok')
    else:
        emit('auth_error', {'message': 'Wrong password'})

@socketio.on('mouse_move')
def handle_mouse_move(data):
    if request.sid not in authenticated_clients:
        return
    dx = data.get('dx', 0)
    dy = data.get('dy', 0)
    sensitivity = data.get('sensitivity', 1.0)
    dx *= sensitivity
    dy *= sensitivity
    try:
        if HAS_QUARTZ and _mouse_held:
            x, y = _mac_mouse_pos()
            if 'left' in _mouse_held:
                _mac_send(kCGEventLeftMouseDragged, x + dx, y + dy, kCGMouseButtonLeft)
            elif 'right' in _mouse_held:
                _mac_send(kCGEventRightMouseDragged, x + dx, y + dy, kCGMouseButtonRight)
        else:
            pyautogui.moveRel(dx, dy, duration=0)
    except Exception:
        pass

@socketio.on('mouse_down')
def handle_mouse_down(data):
    if request.sid not in authenticated_clients:
        return
    button = data.get('button', 'left')
    try:
        if HAS_QUARTZ:
            x, y = _mac_mouse_pos()
            if button == 'left':
                _mac_send(kCGEventLeftMouseDown, x, y, kCGMouseButtonLeft)
            else:
                _mac_send(kCGEventRightMouseDown, x, y, kCGMouseButtonRight)
        else:
            pyautogui.mouseDown(button=button)
        _mouse_held.add(button)
    except Exception:
        pass

@socketio.on('mouse_up')
def handle_mouse_up(data):
    if request.sid not in authenticated_clients:
        return
    button = data.get('button', 'left')
    try:
        if HAS_QUARTZ:
            x, y = _mac_mouse_pos()
            if button == 'left':
                _mac_send(kCGEventLeftMouseUp, x, y, kCGMouseButtonLeft)
            else:
                _mac_send(kCGEventRightMouseUp, x, y, kCGMouseButtonRight)
        else:
            pyautogui.mouseUp(button=button)
        _mouse_held.discard(button)
    except Exception:
        pass

@socketio.on('mouse_click')
def handle_mouse_click(data):
    if request.sid not in authenticated_clients:
        return
    button = data.get('button', 'left')
    try:
        pyautogui.click(button=button)
    except Exception:
        pass

@socketio.on('scroll')
def handle_scroll(data):
    if request.sid not in authenticated_clients:
        return
    dy = data.get('dy', 0)
    dx = data.get('dx', 0)
    try:
        pyautogui.scroll(int(-dy * 3))
        if dx:
            pyautogui.hscroll(int(dx * 3))
    except Exception:
        pass

@socketio.on('gesture_three_finger_drag')
def handle_three_finger_drag(data):
    if request.sid not in authenticated_clients:
        return
    action = data.get('action', '')
    try:
        if action == 'start':
            _mouse_held.add('left')
            if HAS_QUARTZ:
                x, y = _mac_mouse_pos()
                _mac_send(kCGEventLeftMouseDown, x, y, kCGMouseButtonLeft)
            else:
                pyautogui.mouseDown(button='left')
        elif action == 'move':
            dx = data.get('dx', 0) * 2
            dy = data.get('dy', 0) * 2
            if HAS_QUARTZ:
                x, y = _mac_mouse_pos()
                _mac_send(kCGEventLeftMouseDragged, x + dx, y + dy, kCGMouseButtonLeft)
            else:
                pyautogui.moveRel(dx, dy, duration=0)
        elif action == 'end':
            _mouse_held.discard('left')
            if HAS_QUARTZ:
                x, y = _mac_mouse_pos()
                _mac_send(kCGEventLeftMouseUp, x, y, kCGMouseButtonLeft)
            else:
                pyautogui.mouseUp(button='left')
    except Exception:
        pass

@socketio.on('gesture_three_finger_swipe')
def handle_three_finger_swipe(data):
    """macOS 三指滑動對應系統手勢"""
    if request.sid not in authenticated_clients:
        return
    direction = data.get('direction', '')
    try:
        if direction == 'left':
            pyautogui.hotkey('command', 'shift', 'tab')  # 上一個 App
        elif direction == 'right':
            pyautogui.hotkey('command', 'tab')             # 下一個 App
        elif direction == 'up':
            pyautogui.hotkey('ctrl', 'up')                 # Mission Control
        elif direction == 'down':
            pyautogui.hotkey('ctrl', 'down')               # App Exposé
    except Exception:
        pass

@socketio.on('zoom')
def handle_zoom(data):
    if request.sid not in authenticated_clients:
        return
    scale = data.get('scale', 1)
    try:
        if scale < 1:
            pyautogui.keyDown('command')
            pyautogui.scroll(-3)
            pyautogui.keyUp('command')
        else:
            pyautogui.keyDown('command')
            pyautogui.scroll(3)
            pyautogui.keyUp('command')
    except Exception:
        pass

@socketio.on('disconnect')
def handle_disconnect():
    authenticated_clients.discard(request.sid)
    if HAS_QUARTZ and _mouse_held:
        try:
            x, y = _mac_mouse_pos()
            if 'left' in _mouse_held:
                _mac_send(kCGEventLeftMouseUp, x, y, kCGMouseButtonLeft)
            if 'right' in _mouse_held:
                _mac_send(kCGEventRightMouseUp, x, y, kCGMouseButtonRight)
        except Exception:
            pass
    _mouse_held.clear()
    try:
        pyautogui.mouseUp(button='left')
    except Exception:
        pass


class VirtualMouseGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("虛擬滑鼠伺服器")
        self.root.geometry("440x640")
        self.root.resizable(False, False)

        cfg = load_config()
        self.password_var = tk.StringVar()
        self.password_var.set(cfg.get('password', ''))
        self.server_running = False
        self.flask_thread = None
        self.server_ref = None

        self.setup_ui()
        self.update_ip_display()

    def setup_ui(self):
        bg = "#f5f5f5"
        card_bg = "#ffffff"
        fg = "#1a1a2e"
        fg_sub = "#555555"
        accent = "#2563eb"
        font_title = (FONT_FAMILY, 18, "bold")
        font_normal = (FONT_FAMILY, 11)
        font_small = (FONT_FAMILY, 9)
        font_tiny = (FONT_FAMILY, 8)

        self.root.configure(bg=bg)

        tk.Label(self.root, text="虛擬滑鼠伺服器",
                 font=font_title, bg=bg, fg=fg).pack(pady=(16, 4))

        ip_frame = tk.Frame(self.root, bg=bg)
        ip_frame.pack(pady=2)
        tk.Label(ip_frame, text="伺服器 IP:", font=font_normal,
                 bg=bg, fg=fg).pack(side=tk.LEFT)
        self.ip_label = tk.Label(ip_frame, text="", font=font_normal,
                                 fg=accent, bg=bg)
        self.ip_label.pack(side=tk.LEFT, padx=5)

        port_frame = tk.Frame(self.root, bg=bg)
        port_frame.pack(pady=1)
        tk.Label(port_frame, text="連接埠: 8080", font=font_small,
                 fg=fg_sub, bg=bg).pack()

        qr_container = tk.Frame(self.root, bg=card_bg, bd=1, relief=tk.SOLID)
        qr_container.pack(pady=10)
        self.qr_label = tk.Label(qr_container, bg=card_bg)
        self.qr_label.pack(padx=12, pady=12)

        self.url_label = tk.Label(self.root, text="", font=font_small,
                                  fg=fg_sub, bg=bg)
        self.url_label.pack()

        pw_frame = tk.LabelFrame(self.root, text=" 連線密碼 (選填) ",
                                 padx=12, pady=10, bg=card_bg,
                                 font=font_normal, fg=fg)
        pw_frame.pack(pady=8, padx=24, fill=tk.X)

        pw_row = tk.Frame(pw_frame, bg=card_bg)
        pw_row.pack()
        tk.Label(pw_row, text="密碼:", font=font_normal,
                 bg=card_bg, fg=fg).pack(side=tk.LEFT)
        self.pw_entry = tk.Entry(pw_row, textvariable=self.password_var,
                                 show="*", width=18, font=font_normal)
        self.pw_entry.pack(side=tk.LEFT, padx=5)

        self.show_pw_var = tk.IntVar()
        tk.Checkbutton(pw_row, text="顯示", variable=self.show_pw_var,
                       command=self.toggle_password,
                       bg=card_bg, fg=fg, activebackground=card_bg).pack(side=tk.LEFT)

        btn_frame = tk.Frame(self.root, bg=bg)
        btn_frame.pack(pady=10)

        self._start_disabled = False
        self._stop_disabled = True

        self.start_btn = tk.Label(btn_frame, text="  啟動伺服器  ",
                                   bg="#16a34a", fg="white",
                                   font=font_normal, cursor="hand2",
                                   padx=16, pady=6)
        self.start_btn.bind("<Button-1>", lambda e: self.start_server())
        self.start_btn.bind("<Enter>", lambda e: self.start_btn.config(bg="#15803d") if not self._start_disabled else None)
        self.start_btn.bind("<Leave>", lambda e: self.start_btn.config(bg="#16a34a") if not self._start_disabled else None)

        self.stop_btn = tk.Label(btn_frame, text="  停止伺服器  ",
                                  bg="#cccccc", fg="#888888",
                                  font=font_normal, cursor="hand2",
                                  padx=16, pady=6)
        self.stop_btn.bind("<Button-1>", lambda e: self.stop_server() if not self._stop_disabled else None)
        self.stop_btn.bind("<Enter>", lambda e: self.stop_btn.config(bg="#b0b0b0") if not self._stop_disabled else None)
        self.stop_btn.bind("<Leave>", lambda e: self.stop_btn.config(bg="#dc2626") if not self._stop_disabled else self.stop_btn.config(bg="#cccccc"))

        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.status_label = tk.Label(self.root, text="狀態: 已停止",
                                     fg="#dc2626", bg=bg,
                                     font=font_normal)
        self.status_label.pack(pady=2)

        info_btn_frame = tk.Frame(self.root, bg=bg)
        info_btn_frame.pack(pady=4)
        info_btn = tk.Label(info_btn_frame, text="  使用說明  ",
                            bg="#2563eb", fg="white",
                            font=font_normal, cursor="hand2",
                            padx=16, pady=6)
        info_btn.bind("<Button-1>", lambda e: self.show_info())
        info_btn.bind("<Enter>", lambda e: info_btn.config(bg="#1d4ed8"))
        info_btn.bind("<Leave>", lambda e: info_btn.config(bg="#2563eb"))
        info_btn.pack()

        if IS_MAC:
            perm_frame = tk.Frame(self.root, bg="#fff8e1", bd=1, relief=tk.SOLID)
            perm_frame.pack(pady=2, padx=24, fill=tk.X)
            perm = tk.Label(perm_frame,
                            text="需在「系統設定 > 隱私權 > 輔助使用」\n  允許終端機或本 App 的權限",
                            justify=tk.LEFT, bg="#fff8e1",
                            font=font_small, fg="#795548")
            perm.pack(padx=8, pady=6)

        footer_frame = tk.Frame(self.root, bg=bg)
        footer_frame.pack(pady=(2, 8))
        footer = tk.Label(footer_frame,
                          text="Made by 阿剛老師 | 本軟體採用 CC BY-NC 4.0 授權",
                          font=font_tiny, fg=fg_sub, bg=bg, cursor="hand2")
        footer.pack()
        if IS_MAC:
            footer.bind("<Button-1>", lambda e: os.system('open https://kentxchang.blogspot.tw'))
        else:
            footer.bind("<Button-1>", lambda e: os.system('start https://kentxchang.blogspot.tw'))

    def toggle_password(self):
        self.pw_entry.config(show="" if self.show_pw_var.get() else "*")

    def show_info(self):
        win = tk.Toplevel(self.root)
        win.title("使用說明")
        win.geometry("340x420")
        win.resizable(False, False)
        win.configure(bg="#ffffff")
        win.transient(self.root)
        win.grab_set()

        info_text = (
            "使用說明:\n"
            "  1. 點擊「啟動伺服器」\n"
            "  2. 用手機掃描 QR Code\n"
            "  3. 在網頁上使用觸控板\n\n"
            "手勢對應:\n"
            "  1 指拖曳   移動游標\n"
            "  1 指輕點   左鍵點擊\n"
            "  1 指長按   右鍵點擊\n"
            "  2 指拖曳   滾輪捲動\n"
            "  2 指輕點   右鍵點擊\n"
            "  2 指捏合   縮放\n"
            "  3 指輕點   按住左鍵\n"
            "  3 指拖曳   按住左鍵後拖曳\n"
            "  3 指上滑   Mission Control\n"
            "  3 指下滑   App Exposé\n"
            "  3 指左右滑 切換 App"
        )

        tk.Label(win, text="使用說明", font=(FONT_FAMILY, 14, "bold"),
                 bg="#ffffff", fg="#1a1a2e").pack(pady=(16, 8))

        tk.Label(win, text=info_text, justify=tk.LEFT, anchor="nw",
                 bg="#ffffff", fg="#1a1a2e",
                 font=(FONT_FAMILY, 11)).pack(padx=20, pady=(0, 12), fill=tk.BOTH, expand=True)

        close_btn = tk.Label(win, text="  關閉  ", bg="#2563eb", fg="white",
                             font=(FONT_FAMILY, 11), cursor="hand2", padx=20, pady=6)
        close_btn.bind("<Button-1>", lambda e: win.destroy())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#1d4ed8"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#2563eb"))
        close_btn.pack(pady=(0, 16))

    def update_ip_display(self):
        ip = get_local_ip()
        self.ip_label.config(text=ip)
        if self.server_running:
            self.url_label.config(text=f"http://{ip}:8080")
        self.root.after(5000, self.update_ip_display)

    def generate_qr_code(self):
        ip = get_local_ip()
        url = f"http://{ip}:8080"
        qr_img = generate_qr_img(url)
        qr_img = qr_img.resize((180, 180), Image.Resampling.NEAREST)
        self.qr_photo = ImageTk.PhotoImage(qr_img)
        self.qr_label.config(image=self.qr_photo)
        self.url_label.config(text=url)

    def start_server(self):
        if self._start_disabled:
            return
        global password, SERVER_STARTED
        password = self.password_var.get()
        save_config(password)
        self.generate_qr_code()

        self.flask_thread = threading.Thread(target=self.run_server, daemon=True)
        self.flask_thread.start()
        SERVER_STARTED = True

        self.server_running = True
        self._start_disabled = True
        self.start_btn.config(bg="#cccccc", fg="#888888", cursor="")
        self.start_btn.unbind("<Button-1>")
        self.start_btn.unbind("<Enter>")
        self.start_btn.unbind("<Leave>")
        self._stop_disabled = False
        self.stop_btn.config(bg="#dc2626", fg="white", cursor="hand2")
        self.stop_btn.bind("<Button-1>", lambda e: self.stop_server())
        self.stop_btn.bind("<Enter>", lambda e: self.stop_btn.config(bg="#b91c1c") if not self._stop_disabled else None)
        self.stop_btn.bind("<Leave>", lambda e: self.stop_btn.config(bg="#dc2626") if not self._stop_disabled else None)
        self.status_label.config(text="狀態: 執行中", fg="#16a34a")

    def run_server(self):
        try:
            socketio.run(app, host='0.0.0.0', port=8080, debug=False,
                         allow_unsafe_werkzeug=True, use_reloader=False)
        except OSError as e:
            self.root.after(0, lambda: self.status_label.config(
                text=f"狀態: 啟動失敗 ({e})", fg="#dc2626"))

    def stop_server(self):
        if self._stop_disabled:
            return
        global SERVER_STARTED
        self.server_running = False
        SERVER_STARTED = False
        authenticated_clients.clear()
        try:
            if hasattr(socketio, 'stop'):
                socketio.stop()
        except Exception:
            pass
        self._start_disabled = False
        self.start_btn.config(bg="#16a34a", fg="white", cursor="hand2")
        self.start_btn.bind("<Button-1>", lambda e: self.start_server())
        self.start_btn.bind("<Enter>", lambda e: self.start_btn.config(bg="#15803d") if not self._start_disabled else None)
        self.start_btn.bind("<Leave>", lambda e: self.start_btn.config(bg="#16a34a") if not self._start_disabled else None)
        self._stop_disabled = True
        self.stop_btn.config(bg="#cccccc", fg="#888888", cursor="")
        self.stop_btn.unbind("<Button-1>")
        self.stop_btn.unbind("<Enter>")
        self.stop_btn.unbind("<Leave>")
        self.status_label.config(text="狀態: 已停止", fg="#dc2626")
        self.qr_label.config(image="")
        self.url_label.config(text="")


if __name__ == '__main__':
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    root = tk.Tk()
    if IS_MAC:
        try:
            ico = os.path.join(APP_DIR, 'icon.icns')
            if os.path.exists(ico):
                from tkinter import PhotoImage
                img = PhotoImage(file=ico)
                root.iconphoto(True, img)
        except Exception:
            pass
        try:
            ico_png = os.path.join(APP_DIR, 'icon.png')
            if os.path.exists(ico_png):
                from tkinter import PhotoImage
                img = PhotoImage(file=ico_png)
                root.iconphoto(True, img)
        except Exception:
            pass
    else:
        try:
            ico = os.path.join(APP_DIR, 'icon.ico')
            if os.path.exists(ico):
                root.iconbitmap(ico)
        except Exception:
            pass
    gui = VirtualMouseGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))
    root.mainloop()

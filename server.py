#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk
import qrcode
from PIL import Image, ImageTk
import socket
import threading
import os
import sys
import json
import time
import ctypes
import pystray
import logging

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import pyautogui

logging.getLogger('werkzeug').addFilter(
    lambda r: not (r.levelno == logging.ERROR and 'write() before start_response' in r.getMessage()))
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

if getattr(sys, 'frozen', False):
    APP_DIR = sys._MEIPASS
    DATA_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = APP_DIR

TEMPLATE_DIR = os.path.join(APP_DIR, 'templates')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

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
        pyautogui.moveRel(dx, dy, duration=0)
    except Exception:
        pass

@socketio.on('mouse_down')
def handle_mouse_down(data):
    if request.sid not in authenticated_clients:
        return
    button = data.get('button', 'left')
    try:
        pyautogui.mouseDown(button=button)
    except Exception:
        pass

@socketio.on('mouse_up')
def handle_mouse_up(data):
    if request.sid not in authenticated_clients:
        return
    button = data.get('button', 'left')
    try:
        pyautogui.mouseUp(button=button)
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
            pyautogui.mouseDown(button='left')
        elif action == 'move':
            dx = data.get('dx', 0) * 2
            dy = data.get('dy', 0) * 2
            pyautogui.moveRel(dx, dy, duration=0)
        elif action == 'end':
            pyautogui.mouseUp(button='left')
    except Exception:
        pass

@socketio.on('gesture_three_finger_swipe')
def handle_three_finger_swipe(data):
    if request.sid not in authenticated_clients:
        return
    direction = data.get('direction', '')
    try:
        if direction == 'up':
            pyautogui.hotkey('win', 'tab')
        elif direction == 'down':
            pyautogui.hotkey('win', 'd')
        elif direction == 'left':
            pyautogui.hotkey('alt', 'shift', 'tab')
        elif direction == 'right':
            pyautogui.hotkey('alt', 'tab')
    except Exception:
        pass

@socketio.on('zoom')
def handle_zoom(data):
    if request.sid not in authenticated_clients:
        return
    scale = data.get('scale', 1)
    try:
        if scale < 1:
            pyautogui.keyDown('ctrl')
            pyautogui.scroll(-3)
            pyautogui.keyUp('ctrl')
        else:
            pyautogui.keyDown('ctrl')
            pyautogui.scroll(3)
            pyautogui.keyUp('ctrl')
    except Exception:
        pass

@socketio.on('disconnect')
def handle_disconnect():
    authenticated_clients.discard(request.sid)
    try:
        pyautogui.mouseUp(button='left')
    except Exception:
        pass

def get_dpi_scale(root):
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id())
        return dpi / 96.0
    except Exception:
        return 1.0

def scale_val(v, s):
    return max(1, int(round(v * s)))

class VirtualMouseGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Virtual Mouse Server")
        self.root.configure(bg="#f0f0f0")

        cfg = load_config()
        self.password_var = tk.StringVar()
        self.password_var.set(cfg.get('password', ''))
        self.server_running = False
        self.flask_thread = None

        s = get_dpi_scale(root)
        self.s = s
        bw = scale_val(420, s)
        bh = scale_val(640, s)
        self.root.geometry(f"{bw}x{bh}")
        self.root.resizable(False, False)
        self.root.minsize(bw, bh)

        self.setup_ui()
        self.update_ip_display()

    def setup_ui(self):
        s = self.s
        F = lambda pt: ("Microsoft JhengHei", scale_val(pt, s))
        bg = "#f0f0f0"

        tk.Label(self.root, text="🖱 虛擬滑鼠伺服器",
                 font=F(16) + ("bold",), bg=bg).pack(pady=scale_val(12, s))

        ip_frame = tk.Frame(self.root, bg=bg)
        ip_frame.pack(pady=scale_val(2, s))
        tk.Label(ip_frame, text="伺服器 IP:", font=F(11),
                 bg=bg).pack(side=tk.LEFT)
        self.ip_label = tk.Label(ip_frame, text="", font=F(11),
                                 fg="#2563eb", bg=bg)
        self.ip_label.pack(side=tk.LEFT, padx=scale_val(5, s))

        port_frame = tk.Frame(self.root, bg=bg)
        port_frame.pack(pady=scale_val(1, s))
        tk.Label(port_frame, text="連接埠: 5000", font=F(9),
                 fg="gray", bg=bg).pack()

        qr_container = tk.Frame(self.root, bg="white", bd=scale_val(2, s), relief=tk.RIDGE)
        qr_container.pack(pady=scale_val(8, s))
        self.qr_label = tk.Label(qr_container, bg="white")
        pad = scale_val(10, s)
        self.qr_label.pack(padx=pad, pady=pad)

        self.url_label = tk.Label(self.root, text="", font=F(9),
                                  fg="gray", bg=bg)
        self.url_label.pack()

        pw_frame = tk.LabelFrame(self.root, text=" 連線密碼 (選填) ",
                                 padx=scale_val(12, s), pady=scale_val(10, s),
                                 bg=bg, font=F(10))
        pw_frame.pack(pady=scale_val(6, s), padx=scale_val(24, s), fill=tk.X)

        pw_row = tk.Frame(pw_frame, bg=bg)
        pw_row.pack()
        tk.Label(pw_row, text="密碼:", bg=bg, font=F(10)).pack(side=tk.LEFT)
        self.pw_entry = tk.Entry(pw_row, textvariable=self.password_var,
                                 show="*", width=scale_val(18, s), font=F(10))
        self.pw_entry.pack(side=tk.LEFT, padx=scale_val(5, s))

        self.show_pw_var = tk.IntVar()
        tk.Checkbutton(pw_row, text="顯示", variable=self.show_pw_var,
                       command=self.toggle_password, bg=bg).pack(side=tk.LEFT)

        btn_frame = tk.Frame(self.root, bg=bg)
        btn_frame.pack(pady=scale_val(8, s))

        self.start_btn = tk.Button(btn_frame, text="啟動伺服器",
                                   command=self.start_server,
                                   bg="#16a34a", fg="white",
                                   width=scale_val(12, s),
                                   font=F(10) + ("bold",), cursor="hand2")
        self.start_btn.pack(side=tk.LEFT, padx=scale_val(4, s))

        self.stop_btn = tk.Button(btn_frame, text="停止伺服器",
                                  command=self.stop_server,
                                  bg="#dc2626", fg="white",
                                  width=scale_val(12, s),
                                  state=tk.DISABLED, font=F(10) + ("bold",),
                                  cursor="hand2")
        self.stop_btn.pack(side=tk.LEFT, padx=scale_val(4, s))

        self.status_label = tk.Label(self.root, text="狀態: 已停止",
                                     fg="#dc2626", bg=bg,
                                     font=F(10) + ("bold",))
        self.status_label.pack(pady=scale_val(2, s))

        self.gesture_btn = tk.Button(self.root, text="📖 手勢說明",
                                     command=self.show_gesture_popup,
                                     bg="#6366f1", fg="white",
                                     font=F(9) + ("bold",), cursor="hand2")
        self.gesture_btn.pack(pady=scale_val(4, s))

        footer_frame = tk.Frame(self.root, bg=bg)
        footer_frame.pack(pady=scale_val(2, s))
        footer = tk.Label(footer_frame,
                          text="Made by 阿剛老師 | 本軟體採用 CC BY-NC 4.0 授權",
                          font=F(8), fg="#888", bg=bg, cursor="hand2")
        footer.pack()
        footer.bind("<Button-1>", lambda e: os.system('start https://kentxchang.blogspot.tw'))

    def show_gesture_popup(self):
        s = self.s
        F = lambda pt: ("Microsoft JhengHei", scale_val(pt, s))
        top = tk.Toplevel(self.root)
        top.title("手勢說明")
        top.configure(bg="#fef9c3")
        bw = scale_val(360, s)
        bh = scale_val(350, s)
        top.geometry(f"{bw}x{bh}")
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()

        info_text = (
            "使用說明:\n"
            "  1. 點擊「啟動伺服器」\n"
            "  2. 用手機掃描 QR Code\n"
            "  3. 在網頁上使用觸控板\n\n"
            "手勢對應:\n"
            "  \u2022 1 指拖曳  \u2192 移動游標\n"
            "  \u2022 1 指輕點  \u2192 左鍵點擊\n"
            "  \u2022 1 指長按  \u2192 右鍵點擊\n"
            "  \u2022 2 指拖曳  \u2192 滾輪捲動\n"
            "  \u2022 2 指輕點  \u2192 右鍵點擊\n"
            "  \u2022 2 指捏合  \u2192 縮放\n"
            "  \u2022 3 指輕點  \u2192 按住左鍵\n"
            "  \u2022 3 指拖曳  \u2192 左鍵拖曳\n"
            "  \u2022 3 指滑動  \u2192 切換視窗"
        )
        info = tk.Label(top, text=info_text, justify=tk.LEFT,
                        bg="#fef9c3", font=F(9))
        info.pack(padx=scale_val(16, s), pady=scale_val(16, s))

        tk.Button(top, text="關閉", command=top.destroy,
                  bg="#6366f1", fg="white",
                  font=F(9) + ("bold",), cursor="hand2").pack(pady=scale_val(8, s))

    def toggle_password(self):
        self.pw_entry.config(show="" if self.show_pw_var.get() else "*")

    def update_ip_display(self):
        ip = get_local_ip()
        self.ip_label.config(text=ip)
        if self.server_running:
            self.url_label.config(text=f"http://{ip}:5000")
        self.root.after(5000, self.update_ip_display)

    def generate_qr_code(self):
        ip = get_local_ip()
        url = f"http://{ip}:5000"
        qr_img = generate_qr_img(url)
        qs = scale_val(180, self.s)
        qr_img = qr_img.resize((qs, qs), Image.Resampling.NEAREST)
        self.qr_photo = ImageTk.PhotoImage(qr_img)
        self.qr_label.config(image=self.qr_photo)
        self.url_label.config(text=url)

    def setup_tray(self):
        ico_path = os.path.join(APP_DIR, 'icon.ico')
        if not os.path.exists(ico_path):
            return
        img = Image.open(ico_path)
        menu = pystray.Menu(
            pystray.MenuItem("顯示視窗", self.show_window, default=True),
            pystray.MenuItem("結束", self.quit_app),
        )
        self.tray_icon = pystray.Icon("virtual_mouse", img, "虛擬滑鼠伺服器", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def show_window(self, icon=None, item=None):
        if icon:
            icon.stop()
        self.tray_minimized = False
        self.root.after(0, self._restore_window)

    def _restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_minimize(self):
        if getattr(self, 'tray_minimized', False):
            return
        self.tray_minimized = True
        self.root.withdraw()
        if not hasattr(self, 'tray_icon') or not self.tray_icon:
            self.setup_tray()

    def quit_app(self, icon=None, item=None):
        if icon:
            icon.stop()
        self.root.after(100, lambda: os._exit(0))

    def start_server(self):
        global password, SERVER_STARTED
        password = self.password_var.get()
        save_config(password)
        self.generate_qr_code()

        self.flask_thread = threading.Thread(target=self.run_server, daemon=True)
        self.flask_thread.start()
        SERVER_STARTED = True

        self.server_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_label.config(text="狀態: 執行中", fg="#16a34a")

    def run_server(self):
        socketio.run(app, host='0.0.0.0', port=5000, debug=False,
                     allow_unsafe_werkzeug=True, use_reloader=False)

    def stop_server(self):
        os._exit(0)

if __name__ == '__main__':
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    root = tk.Tk()
    try:
        ico = os.path.join(APP_DIR, 'icon.ico')
        if os.path.exists(ico):
            root.iconbitmap(ico)
    except Exception:
        pass
    gui = VirtualMouseGUI(root)
    orig_iconify = root.iconify
    def tray_minimize():
        gui.on_minimize()
        gui.tray_minimized = True
    root.iconify = tray_minimize
    root.protocol("WM_DELETE_WINDOW", tray_minimize)
    root.mainloop()

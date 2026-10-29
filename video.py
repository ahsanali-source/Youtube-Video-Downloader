import customtkinter as ctk
from tkinter import messagebox, filedialog
import yt_dlp
import threading
import os
import sqlite3
import re
import webbrowser
from datetime import datetime
import time

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect("download_history.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS history 
                      (id INTEGER PRIMARY KEY, name TEXT, type TEXT, status TEXT, date TEXT, file_path TEXT)''')
    
    cursor.execute("PRAGMA table_info(history)")
    columns = [column[1] for column in cursor.fetchall()]
    if "file_path" not in columns:
        cursor.execute("ALTER TABLE history ADD COLUMN file_path TEXT DEFAULT ''")
        
    conn.commit()
    conn.close()

def add_to_history(name, file_type, status, file_path=""):
    conn = sqlite3.connect("download_history.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO history (name, type, status, date, file_path) VALUES (?, ?, ?, ?, ?)", 
                   (name, file_type, status, now, file_path))
    conn.commit()
    conn.close()

def delete_from_db(file_path):
    conn = sqlite3.connect("download_history.db")
    cursor = conn.cursor()
    # Match both windows absolute paths safely
    cursor.execute("DELETE FROM history WHERE file_path=? OR name=?", (file_path, file_path))
    conn.commit()
    conn.close()

def clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


# --- Notification Pop-up Window ---
class DownloadCompleteWindow(ctk.CTkToplevel):
    def __init__(self, title, file_path, callback_reset):
        super().__init__()
        self.title("Download Complete")
        self.geometry("450x200")
        self.resizable(False, False)
        self.attributes("-topmost", True) 
        self.file_path = file_path
        self.callback_reset = callback_reset # Reset dashboard fields on close
        
        ctk.CTkLabel(self, text="🎉 Download Successful!", font=("Arial", 16, "bold"), text_color="#2ecc71").pack(pady=15)
        lbl_name = ctk.CTkLabel(self, text=title, font=("Arial", 12), wraplength=400)
        lbl_name.pack(pady=5, padx=10)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        self.p_btn = ctk.CTkButton(btn_frame, text="▶ Play File", fg_color="#27ae60", width=120, command=self.play_now)
        self.p_btn.pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="📂 Open Folder", fg_color="#2980b9", width=120, command=self.open_dir).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Close", fg_color="gray", width=80, command=self.close_popup).pack(side="left", padx=10)
        
        self.p_btn.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.close_popup)

    def play_now(self):
        if os.path.exists(self.file_path):
            os.startfile(self.file_path)
            self.close_popup()
        else:
            messagebox.showerror("Error", "File not found!")

    def open_dir(self):
        if os.path.exists(self.file_path):
            os.system(f'explorer /selectItems,"{os.path.abspath(self.file_path)}"')
            self.close_popup()
        else:
            messagebox.showerror("Error", "Folder not found!")

    def close_popup(self):
        self.callback_reset() # Clear main form inputs completely
        self.destroy()


# --- Main Application Window ---
class YVD_App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YVD - Youtube Video Downloader")
        self.geometry("1040x680") 
        
        self.download_path = os.path.join(os.path.expanduser("~"), "Desktop")
        init_db()
        
        # Navigation History Tracking
        self.nav_history = ["Dashboard"]
        self.nav_index = 0
        self.is_paused = False
        self.last_checked_url = "" # Prevent loop fetch on same URL

        # Row Tracking For Selection Mechanics
        self.row_frames = []
        self.selected_rows = set()
        self.focused_row_index = -1

        # Global Application Keybindings
        self.bind("<Delete>", lambda e: self.trigger_keyboard_delete())
        self.bind("<Control-a>", lambda e: self.select_all_visible_rows())
        self.bind("<Control-A>", lambda e: self.select_all_visible_rows())
        self.bind("<Up>", lambda e: self.move_row_focus(-1))
        self.bind("<Down>", lambda e: self.move_row_focus(1))

        # --- SIDEBAR LAYOUT ---
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="YVD ENGINE", font=("Arial", 20, "bold"), text_color="#3498db")
        self.logo_label.pack(pady=25)

        # Core Controls
        self.tools_title = ctk.CTkLabel(self.sidebar, text="⚙️ Tools", font=("Arial", 16, "bold"), anchor="w")
        self.tools_title.pack(fill="x", padx=15, pady=(15, 5))

        self.btn_download = ctk.CTkButton(self.sidebar, text="Main Menu", font=("Arial", 14, "bold"), fg_color="#2980b9", hover_color="#3498db", height=35, command=lambda: self.navigate_to("Dashboard"))
        self.btn_download.pack(pady=5, padx=15, fill="x")
        
        # Categories Section
        self.cat_title = ctk.CTkLabel(self.sidebar, text="📁 Categories", font=("Arial", 13, "bold"), anchor="w")
        self.cat_title.pack(fill="x", padx=15, pady=(10, 5))
        
        self.btn_all = ctk.CTkButton(self.sidebar, text="  ↳ All Downloads", anchor="w", fg_color="transparent", text_color="white", hover_color="#2c3e50", height=32, command=lambda: self.navigate_to("All"))
        self.btn_all.pack(fill="x", padx=15)

        self.btn_video_cat = ctk.CTkButton(self.sidebar, text="  ↳ 🎬 Videos", anchor="w", fg_color="transparent", text_color="white", hover_color="#2c3e50", height=32, command=lambda: self.navigate_to("video"))
        self.btn_video_cat.pack(fill="x", padx=15)

        self.btn_audio_cat = ctk.CTkButton(self.sidebar, text="  ↳ 🎵 Audio Songs", anchor="w", fg_color="transparent", text_color="white", hover_color="#2c3e50", height=32, command=lambda: self.navigate_to("audio"))
        self.btn_audio_cat.pack(fill="x", padx=15)

        self.btn_fin_cat = ctk.CTkButton(self.sidebar, text="  ↳ ✅ Finished", anchor="w", fg_color="transparent", text_color="white", hover_color="#2c3e50", height=32, command=lambda: self.navigate_to("Success"))
        self.btn_fin_cat.pack(fill="x", padx=15)

        self.btn_unfin_cat = ctk.CTkButton(self.sidebar, text="  ↳ ❌ Unfinished", anchor="w", fg_color="transparent", text_color="white", hover_color="#2c3e50", height=32, command=lambda: self.navigate_to("Failed"))
        self.btn_unfin_cat.pack(fill="x", padx=15)

        #------------------------ SHARE / RECOMMEND BUTTON WITH GITHUB LINK ---

        self.github_url = "https://github.com/ahsanali-source/Youtube-Video-Downloader" 
        self.btn_share = ctk.CTkButton(self.sidebar, text="✨ Recommend YVD", fg_color="#27ae60", hover_color="#2ecc71", font=("Arial", 11, "bold"), height=35, command=self.open_github)
        self.btn_share.pack(side="bottom", pady=25, padx=15, fill="x")

        # --- TOP CONTROL BAR ---
        self.top_bar = ctk.CTkFrame(self, height=50, fg_color="transparent")
        self.top_bar.pack(side="top", fill="x", padx=20, pady=(10, 0))

        self.btn_back = ctk.CTkButton(self.top_bar, text="🡨", width=35, height=35, fg_color="#34495e", font=("Arial", 16, "bold"), command=self.go_back)
        self.btn_back.pack(side="left", padx=2)
        
        self.btn_forward = ctk.CTkButton(self.top_bar, text="🡪", width=35, height=35, fg_color="#34495e", font=("Arial", 16, "bold"), command=self.go_forward)
        self.btn_forward.pack(side="left", padx=2)

        self.current_view_lbl = ctk.CTkLabel(self.top_bar, text="Dashboard Panel", font=("Arial", 14, "bold"), text_color="#3498db")
        self.current_view_lbl.pack(side="left", padx=20)

        # --- MAIN PANEL CONTAINER ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(side="right", fill="both", expand=True, padx=25, pady=10)
        
        self.render_dashboard()

    def navigate_to(self, view_name):
        if self.nav_history[self.nav_index] != view_name:
            self.nav_history = self.nav_history[:self.nav_index + 1]
            self.nav_history.append(view_name)
            self.nav_index = len(self.nav_history) - 1
        self.load_view(view_name)

    def go_back(self):
        if self.nav_index > 0:
            self.nav_index -= 1
            self.load_view(self.nav_history[self.nav_index])

    def go_forward(self):
        if self.nav_index < len(self.nav_history) - 1:
            self.nav_index += 1
            self.load_view(self.nav_history[self.nav_index])

    def load_view(self, name):
        self.current_view_lbl.configure(text=f"View: {name.capitalize()}")
        if name == "Dashboard":
            self.render_dashboard()
        else:
            self.render_history_log_view(filter_mode=name)

    def open_github(self):
        webbrowser.open(self.github_url)

    def render_dashboard(self):
        for widget in self.main_frame.winfo_children(): widget.destroy()
        
        ctk.CTkLabel(self.main_frame, text="YVD Pro Download Dashboard", font=("Arial", 24, "bold")).pack(pady=10)
        
        # URL Input Field
        self.url_entry = ctk.CTkEntry(self.main_frame, placeholder_text="Paste link here (Auto-fetching enabled)...", width=550, height=38)
        self.url_entry.pack(pady=10)
        self.url_entry.focus_set()
        
        # Start background automatic listener loop for link changes
        self.url_entry.bind("<KeyRelease>", lambda e: self.check_url_change())

        self.quality_menu = ctk.CTkOptionMenu(self.main_frame, values=["Waiting for link paste..."], width=250, height=32)
        self.quality_menu.pack(pady=5)
        
        self.path_display = ctk.CTkLabel(self.main_frame, text=f"Output Folder: {self.download_path}", text_color="gray")
        self.path_display.pack(pady=5)
        
        ctk.CTkButton(self.main_frame, text="Select Save Directory", command=self.change_path, fg_color="#555555", width=200).pack(pady=2)
        
        # --- PROGRESS PACK (Paired Side-by-Side horizontally with pause button) ---
        bars_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        bars_container.pack(pady=15, fill="x", padx=40)

        left_progress_panel = ctk.CTkFrame(bars_container, fg_color="transparent")
        left_progress_panel.pack(side="left", fill="x", expand=True)

        self.lbl_bar1 = ctk.CTkLabel(left_progress_panel, text="Download Progress: 0%", font=("Arial", 11, "bold"), anchor="w")
        self.lbl_bar1.pack(fill="x")
        self.prog_bar = ctk.CTkProgressBar(left_progress_panel, height=16, progress_color="#2ecc71")
        self.prog_bar.set(0)
        self.prog_bar.pack(fill="x", pady=(2, 8))
        
        self.lbl_bar2 = ctk.CTkLabel(left_progress_panel, text="Data Processed: 0.00 MB / 0.00 MB", font=("Arial", 11), anchor="w")
        self.lbl_bar2.pack(fill="x")
        self.size_bar = ctk.CTkProgressBar(left_progress_panel, height=16, progress_color="#3498db")
        self.size_bar.set(0)
        self.size_bar.pack(fill="x", pady=(2, 0))

        # Pause Control Button shifted to Right Side of Progress layouts
        self.btn_pause = ctk.CTkButton(bars_container, text="⏸ Pause", command=self.toggle_pause, fg_color="#d35400", hover_color="#e67e22", width=100, height=55, font=("Arial", 12, "bold"), state="disabled")
        self.btn_pause.pack(side="right", padx=(20, 0), pady=(15, 0))

        self.status_label = ctk.CTkLabel(self.main_frame, text="Status: Waiting for input URL string stream...", font=("Arial", 12, "italic"), text_color="gray")
        self.status_label.pack(pady=10)

        btn_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        btn_container.pack(pady=10)
        
        self.dl_v_btn = ctk.CTkButton(btn_container, text="🎬 Download Video", command=lambda: self.start_dl("video"), fg_color="#1f538d", height=42, width=180, state="disabled", font=("Arial", 12, "bold"))
        self.dl_v_btn.pack(side="left", padx=15)
        
        self.dl_a_btn = ctk.CTkButton(btn_container, text="🎵 Download Audio", command=lambda: self.start_dl("audio"), fg_color="#2c6e49", height=42, width=180, state="disabled", font=("Arial", 12, "bold"))
        self.dl_a_btn.pack(side="left", padx=15)

    # Automatically polls link state change
    def check_url_change(self):
        url = self.url_entry.get().strip()
        # Trigger fetch engine instantly if a valid youtube link format is encountered
        if url and url != self.last_checked_url and ("youtube.com" in url or "youtu.be" in url):
            self.last_checked_url = url
            self.status_label.configure(text="Status: Detecting url stream... Fetching options automatically.", text_color="#f1c40f")
            threading.Thread(target=self.analyze_link_logic, args=(url,), daemon=True).start()


#--------------------------------------- HISTORY LOG VIEW RENDERING WITH SELECTION MECHANICS AND INLINE ACTIONS ---------

    def render_history_log_view(self, filter_mode="All"):
        for widget in self.main_frame.winfo_children(): widget.destroy()
        
        self.row_frames = []
        self.selected_rows.clear()
        self.focused_row_index = -1

        scroll_frame = ctk.CTkScrollableFrame(self.main_frame, width=700, height=480)
        scroll_frame.pack(pady=10, fill="both", expand=True)
        
        conn = sqlite3.connect("download_history.db")
        cursor = conn.cursor()
        
        if filter_mode == "All":
            cursor.execute("SELECT name, type, status, date, file_path FROM history ORDER BY id DESC")
        elif filter_mode in ["video", "audio"]:
            cursor.execute("SELECT name, type, status, date, file_path FROM history WHERE type=? ORDER BY id DESC", (filter_mode,))
        elif filter_mode in ["Success", "Failed"]:
            cursor.execute("SELECT name, type, status, date, file_path FROM history WHERE status=? ORDER BY id DESC", (filter_mode,))
            
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            ctk.CTkLabel(scroll_frame, text="No items inside this folder logs view.", font=("Arial", 14, "italic")).pack(pady=30)
            return

        # FIXED reference point to freeze the main application context safely
        app_instance = self

        for idx, r in enumerate(rows):
            path_key = r[4] if r[4] else r[0] 
            
            item_frame = ctk.CTkFrame(scroll_frame, fg_color="#2c3e50" if idx % 2 == 0 else "#34495e")
            item_frame.pack(fill="x", pady=4, padx=8)
            
            item_frame.bind("<Button-1>", lambda e, p=path_key, i=idx: app_instance.toggle_row_selection(p, i, e))
            
            icon = "🎬 [VIDEO]" if r[1] == "video" else "🎵 [AUDIO]"
            info_text = f"{icon}  {r[0][:50]}...  ({r[2]}) \nDate: {r[3]}"
            
            lbl = ctk.CTkLabel(item_frame, text=info_text, font=("Arial", 11), justify="left", anchor="w")
            lbl.pack(side="left", padx=15, pady=8, fill="x", expand=True)
            lbl.bind("<Button-1>", lambda e, p=path_key, i=idx: app_instance.toggle_row_selection(p, i, e))
            
            btn_div = ctk.CTkFrame(item_frame, fg_color="transparent")
            btn_div.pack(side="right", padx=5)

            # FIXED: Lambda explicit instance callback locking
            # 'app_instance' ko closure mein pass karne se 'self' ka context kabhi corrupt nahi hoga
            if r[2] == "Success" and r[4]:
                target_path = r[4]
                ctk.CTkButton(btn_div, text="▶ Play", width=65, height=24, fg_color="#27ae60", command=lambda p=target_path: app_instance.play_file(p)).pack(side="left", padx=2)
                ctk.CTkButton(btn_div, text="📂 Folder", width=65, height=24, fg_color="#2980b9", command=lambda p=target_path: app_instance.open_folder_of_file(p)).pack(side="left", padx=2)

            ctk.CTkButton(btn_div, text="🗑 Delete", width=65, height=24, fg_color="#c0392b", command=lambda p=path_key: app_instance.inline_row_delete(p, filter_mode)).pack(side="left", padx=2)

            self.row_frames.append({'frame': item_frame, 'path': path_key, 'default_color': item_frame.cget("fg_color")})

    def toggle_row_selection(self, path, index, event=None):
        if event and event.state & 0x0001: 
            if self.focused_row_index != -1:
                start = min(self.focused_row_index, index)
                end = max(self.focused_row_index, index)
                for i in range(start, end + 1):
                    p = self.row_frames[i]['path']
                    self.selected_rows.add(p)
                    self.row_frames[i]['frame'].configure(fg_color="#16a085")
                return

        self.focused_row_index = index
        if path in self.selected_rows:
            self.selected_rows.remove(path)
            self.row_frames[index]['frame'].configure(fg_color=self.row_frames[index]['default_color'])
        else:
            self.selected_rows.add(path)
            self.row_frames[index]['frame'].configure(fg_color="#16a085")

    def select_all_visible_rows(self):
        if not self.row_frames: return
        for item in self.row_frames:
            self.selected_rows.add(item['path'])
            item['frame'].configure(fg_color="#16a085")

    def move_row_focus(self, direction):
        if not self.row_frames: return
        target = self.focused_row_index + direction
        if 0 <= target < len(self.row_frames):
            if self.focused_row_index != -1 and self.row_frames[self.focused_row_index]['path'] not in self.selected_rows:
                self.row_frames[self.focused_row_index]['frame'].configure(fg_color=self.row_frames[self.focused_row_index]['default_color'])
            
            self.focused_row_index = target
            self.row_frames[target]['frame'].configure(fg_color="#34495e")
            self.row_frames[target]['frame'].focus_set()

    def trigger_keyboard_delete(self):
        if not self.selected_rows: return
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {len(self.selected_rows)} selected log record(s)?"):
            for path in list(self.selected_rows):
                delete_from_db(path)
            self.render_history_log_view(self.nav_history[self.nav_index])

    def inline_row_delete(self, path, current_filter):
        if messagebox.askyesno("Confirm Delete", "Delete this download record from database logs?"):
            delete_from_db(path)
            self.render_history_log_view(current_filter)

    def analyze_link_logic(self, url):
        try:
            ydl_opts = {'quiet': True, 'nocolors': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get('formats', [])
                resolutions = set()
                
                for f in formats:
                    if f.get('height') and f.get('vcodec') != 'none':
                        resolutions.add(f.get('height'))
                
                sorted_res = sorted(list(resolutions), reverse=True)
                menu_values = []
                
                # YOUR SMART IDEA IMPLEMENTED: Mapping real video heights to standard IDM-style labels
                for res in sorted_res:
                    # 4K Range (e.g., 1920 to 2180 vertical lines)
                    if 1900 <= res <= 2180:
                        if "2160p (4K)" not in menu_values: menu_values.append("2160p (4K)")
                    # 2K / 1440p Range
                    elif 1300 <= res <= 1460:
                        if "1440p (2K)" not in menu_values: menu_values.append("1440p (2K)")
                    # Full HD / 1080p Range (Handles cinematic crops like 800p or 816p cleanly)
                    elif 800 <= res <= 1080:
                        if "1080p (FHD)" not in menu_values: menu_values.append("1080p (FHD)")
                    # HD / 720p Range
                    elif 550 <= res <= 799:
                        if "720p (HD)" not in menu_values: menu_values.append("720p (HD)")
                    # 480p Range
                    elif 400 <= res <= 549:
                        if "480p" not in menu_values: menu_values.append("480p")
                    # 360p Range
                    elif 300 <= res <= 399:
                        if "360p" not in menu_values: menu_values.append("360p")
                    # Fallback for very small formats
                    elif res < 300:
                        if f"{res}p" not in menu_values: menu_values.append(f"{res}p")
                
                if not menu_values: 
                    menu_values = ["720p (HD)"] # Safe default if nothing found

                # Send cleanly categorized elements to UI thread
                self.after(0, lambda: self.update_ui_after_analysis(menu_values))
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(text="Status: Auto-fetch analysis failed.", text_color="#e74c3c"))
        # Removed hard block to avoid locking UI controls unexpectedly

    def update_ui_after_analysis(self, values):
        self.quality_menu.configure(values=values)
        self.quality_menu.set(values[0])
        self.dl_v_btn.configure(state="normal")
        self.dl_a_btn.configure(state="normal")
        self.status_label.configure(text="Status: Extraction completed! Ready to process stream.", text_color="#2ecc71")

    def toggle_pause(self):
        if not self.is_paused:
            self.is_paused = True
            self.btn_pause.configure(text="▶ Resume", fg_color="#27ae60")
            self.status_label.configure(text="Status: Download Paused", text_color="#e67e22")
        else:
            self.is_paused = False
            self.btn_pause.configure(text="⏸ Pause", fg_color="#d35400")
            self.status_label.configure(text="Status: Processing data pipeline active...", text_color="#3498db")

    def change_path(self):
        new_path = filedialog.askdirectory()
        if new_path:
            self.download_path = new_path
            self.path_display.configure(text=f"Output Folder: {new_path}")

    def start_dl(self, mode):
        url = self.url_entry.get()
        if not url: return
        self.dl_v_btn.configure(state="disabled")
        self.dl_a_btn.configure(state="disabled")
        self.btn_pause.configure(state="normal")
        threading.Thread(target=self.download_logic, args=(url, mode), daemon=True).start()

    def download_logic(self, url, mode):
        quality_text = self.quality_menu.get().split(" ")[0]
        quality = quality_text.replace("p", "")
        
        # 1. Title aur Extension ka base template setup
        template = os.path.join(self.download_path, f'%(title)s_{quality}p.%(ext)s')
        
        ydl_opts = {
            'outtmpl': template, 
            'progress_hooks': [self.hook], 
            'quiet': True, 
            'nocolors': True, 
            'no_warnings': True,
        }
        
        if mode == "video":
            ydl_opts['format'] = (
                f"bestvideo[height={quality}][vcodec^=avc1]+bestaudio[ext=m4a]/"
                f"bestvideo[height={quality}]+bestaudio/"
                f"bestvideo[height<={quality}]+bestaudio/"
                f"best[height<={quality}]/"
                f"best"
            )
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['postprocessor_args'] = {
                'video_convertor': ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest']
            }
        else:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio', 
                'preferredcodec': 'mp3', 
                'preferredquality': '192'
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Unknown Title')
                
                # 2. Extracting the real final filename that yt-dlp generated on disk
                raw_filename = ydl.prepare_filename(info)
                
                # 3. FIXED: Extracting base path and injecting exact clean extension formats
                base_ext = ".mp3" if mode == "audio" else ".mp4"
                clean_filename_base = os.path.splitext(raw_filename)[0]
                
                # Check if resolution tag is already inside the filename, if not, append safely
                if f"_{quality}p" not in clean_filename_base:
                    final_file_path = f"{clean_filename_base}_{quality}p{base_ext}"
                else:
                    final_file_path = f"{clean_filename_base}{base_ext}"
                
                # 4. Enforcing exact system absolute path format compatibility for Windows Explorer
                final_absolute_path = os.path.normpath(os.path.abspath(final_file_path))
                
                # Save the exact matching title and path to SQLite database
                add_to_history(title, mode, "Success", final_absolute_path)
            
            # Update Progress indicators smoothly to completion
            self.prog_bar.set(1)
            self.size_bar.set(1)
            self.lbl_bar1.configure(text="Download Progress: 100%")
            
            # Launch clean success popup layout window
            self.after(0, lambda: DownloadCompleteWindow(title, final_absolute_path, self.reset_dashboard_fields))
        except Exception as e:
            add_to_history(url[:30], mode, "Failed", "")
            messagebox.showerror("Download Error", f"An issue occurred: {e}")
            self.after(0, self.reset_dashboard_fields)
        finally:
            self.dl_v_btn.configure(state="normal")
            self.dl_a_btn.configure(state="normal")

    # Completely cleans up fields for next operations cleanly
    def reset_dashboard_fields(self):
        self.url_entry.delete(0, 'end')
        self.last_checked_url = ""
        self.quality_menu.configure(values=["Waiting for link paste..."])
        self.quality_menu.set("Waiting for link paste...")
        self.prog_bar.set(0)
        self.size_bar.set(0)
        self.lbl_bar1.configure(text="Download Progress: 0%")
        self.lbl_bar2.configure(text="Data Processed: 0.00 MB / 0.00 MB")
        self.status_label.configure(text="Status: Engine Idle", text_color="gray")
        self.dl_v_btn.configure(state="disabled")
        self.dl_a_btn.configure(state="disabled")
        self.btn_pause.configure(state="disabled", text="⏸ Pause", fg_color="#d35400")

    def hook(self, d):
        # HARD CORE PAUSE CHECK: Jab tak is_paused True rahega, yeh hook download thread ko aage nahi barhne dega
        while self.is_paused:
            time.sleep(0.1) # Fast checking intervals to prevent lag on resume
            
        if d['status'] == 'downloading':
            p_raw = d.get('_percent_str', '0%')
            p_clean = clean_ansi(p_raw).replace('%', '').strip()
            downloaded = d.get('downloaded_bytes', 0) / (1024*1024)
            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            total_mb = total / (1024*1024)
            speed_str = d.get('_speed_str', 'N/A')
            try:
                p_float = float(p_clean)
                self.prog_bar.set(p_float / 100)
                self.lbl_bar1.configure(text=f"Download Progress: {p_clean}%")
                if total_mb > 0: self.size_bar.set(downloaded / total_mb)
                self.lbl_bar2.configure(text=f"Data: {downloaded:.2f} MB / {total_mb:.2f} MB ({clean_ansi(speed_str)})")
            except: pass

if __name__ == "__main__":
    app = YVD_App()
    app.mainloop()

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont
import threading
import os
import datetime
import tempfile
import hashlib
import wave
import re

# gTTS import
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    print("⚠️ gTTS nincs telepítve")

# Pygame import
import pygame

class FaternakFelolvasoProgram:
    def __init__(self):
        # Főablak - NAGYOBB!
        self.root = tk.Tk()
        self.root.title("🎤 Faternak felolvasóprogram")
        self.root.geometry("900x800")  # NAGYOBB ABLAK!
        self.root.configure(bg='#2b2b2b')
        
        # Már nincs szükség API kulcsra - gTTS ingyenes!
        # self.api_key = "AIzaSyC-XjlcBSMuuqA-W4u1hkHQhTqA3Oj9GUY"
        
        # TTS beállítások - CSAK gTTS
        if not GTTS_AVAILABLE:
            raise Exception("gTTS nincs telepítve! pip install gtts")
        
        self.tts_method = "gtts"
        print("🎯 gTTS aktiválva (hosszú szövegek támogatásával)")
        
        # Hosszú szöveg kezelés
        self.max_chunk_length = 500  # gTTS-nek kisebb részek kellenek
        self.audio_chunks = []  # Generált audio részek
        self.current_chunk_index = 0
        self.total_chunks = 0
        
        # Audio mappa létrehozása Documents-ben
        self.audio_dir = os.path.join(os.path.expanduser("~"), "Documents", "Felolvasott_szovegek")
        os.makedirs(self.audio_dir, exist_ok=True)
        
        # Audio változók
        pygame.mixer.init()
        self.is_playing = False
        self.current_audio_file = None
        self.current_text = ""
        
        # STOP FLAG - Generálás leállítása
        self.generation_active = False
        self.stop_requested = False
        
        # Fontok
        self.title_font = tkfont.Font(family="Arial", size=20, weight="bold")
        self.button_font = tkfont.Font(family="Arial", size=12, weight="bold")
        self.text_font = tkfont.Font(family="Arial", size=11)
        
        self.setup_ui()
        
    def setup_ui(self):
        # Főkeret
        main_frame = tk.Frame(self.root, bg='#2b2b2b', padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Cím
        title_label = tk.Label(
            main_frame,
            text="🎤 Faternak felolvasóprogram",
            font=self.title_font,
            fg="white",
            bg="#2b2b2b"
        )
        title_label.pack(pady=(0, 10))
        
        subtitle_label = tk.Label(
            main_frame,
            text="Húzd ide a .txt fájlt vagy kattints a betöltéshez",
            font=self.text_font,
            fg="lightgray",
            bg="#2b2b2b"
        )
        subtitle_label.pack(pady=(0, 20))
        
        # *** PROGRESS BAR SECTION - FELÜL! ***
        progress_frame = tk.Frame(main_frame, bg="#3c3c3c", relief="ridge", bd=3)
        progress_frame.pack(fill="x", pady=(0, 20), padx=10)
        
        # Progress címke
        progress_title = tk.Label(
            progress_frame,
            text="📊 FELOLVASÁS ÁLLAPOTA",
            font=tkfont.Font(size=16, weight="bold"),
            fg="white",
            bg="#3c3c3c"
        )
        progress_title.pack(pady=(15, 5))
        
        # Progress info label - NAGY BETŰK
        self.progress_label = tk.Label(
            progress_frame,
            text="Várj a fájl betöltésére...",
            font=tkfont.Font(size=14, weight="bold"),
            fg="#FF9800",
            bg="#3c3c3c"
        )
        self.progress_label.pack(pady=5)
        
        # NAGY Progress bar - mindig látható
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            mode='determinate',
            variable=self.progress_var,
            maximum=100,
            length=500,  # MÉG SZÉLESEBB
            style="TProgressbar"
        )
        self.progress_bar.pack(fill="x", padx=30, pady=(10, 5))
        
        # Progress percentages - NAGY SZÁMOK
        self.progress_percent = tk.Label(
            progress_frame,
            text="0%",
            font=tkfont.Font(size=18, weight="bold"),
            fg="#4CAF50",
            bg="#3c3c3c"
        )
        self.progress_percent.pack(pady=(5, 15))
        
        # VEZÉRLŐ GOMBOK
        control_frame = tk.Frame(main_frame, bg="#2b2b2b")
        control_frame.pack(fill="x", pady=(0, 20))
        
        control_label = tk.Label(
            control_frame,
            text="🎵 Audio vezérlés:",
            font=tkfont.Font(size=14, weight="bold"),
            fg="white",
            bg="#2b2b2b",
            anchor="w"
        )
        control_label.pack(fill="x", pady=(0, 10))
        
        # Gombok keret
        buttons_frame = tk.Frame(control_frame, bg="#2b2b2b")
        buttons_frame.pack()
        
        # Felolvasás gomb (KEZDETBEN LETILTVA) - NAGY ÉS SZÉP
        self.read_aloud_btn = tk.Button(
            buttons_frame,
            text="📢 OLVASD FEL",
            command=self.read_aloud,
            font=tkfont.Font(size=16, weight="bold"),
            bg="#2d8f2d",
            fg="white",
            relief="flat",
            padx=30,
            pady=15,
            state="disabled"
        )
        self.read_aloud_btn.pack(side="left", padx=(0, 20))
        
        # Generálás gomb (KEZDETBEN LETILTVA)
        self.generate_btn = tk.Button(
            buttons_frame,
            text="🎵 Felolvasás készítése",
            command=self.generate_audio,
            font=self.button_font,
            bg="#1f538d",
            fg="white",
            relief="flat",
            padx=20,
            pady=12,
            state="disabled"
        )
        self.generate_btn.pack(side="left", padx=(0, 15))
        
        # Lejátszás gomb
        self.play_btn = tk.Button(
            buttons_frame,
            text="▶️ Lejátszás",
            command=self.play_audio,
            font=self.button_font,
            bg="#2d8f2d",
            fg="white",
            relief="flat",
            padx=15,
            pady=12,
            state="disabled"
        )
        self.play_btn.pack(side="left", padx=(0, 15))
        
        # Stop gomb
        self.stop_btn = tk.Button(
            buttons_frame,
            text="⏹️ Stop",
            command=self.stop_audio,
            font=self.button_font,
            bg="#b83c3c",
            fg="white",
            relief="flat",
            padx=15,
            pady=12,
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(0, 15))
        
        # Mentés gomb
        self.save_btn = tk.Button(
            buttons_frame,
            text="💾 Mentés",
            command=self.save_audio,
            font=self.button_font,
            bg="gray",
            fg="white",
            relief="flat",
            padx=15,
            pady=12,
            state="disabled"
        )
        self.save_btn.pack(side="left")
        
        # Fájl betöltő keret
        file_frame = tk.Frame(main_frame, bg="#3c3c3c", relief="ridge", bd=2)
        file_frame.pack(fill="x", pady=(0, 20), ipady=30)
        
        # Fájl slot
        self.file_icon_label = tk.Label(
            file_frame,
            text="📄",
            font=tkfont.Font(size=40),
            fg="white",
            bg="#3c3c3c"
        )
        self.file_icon_label.pack()
        
        self.file_status_label = tk.Label(
            file_frame,
            text="Nincs fájl betöltve\nKattints ide vagy húzd ide a .txt fájlt",
            font=self.text_font,
            fg="lightgray",
            bg="#3c3c3c",
            justify="center"
        )
        self.file_status_label.pack(pady=5)
        
        # Fájl betöltő gomb
        load_btn = tk.Button(
            file_frame,
            text="📁 Fájl kiválasztása",
            command=self.load_file,
            font=self.button_font,
            bg="#4CAF50",
            fg="white",
            relief="flat",
            padx=20,
            pady=8
        )
        load_btn.pack(pady=10)
        
        # Szöveg előnézet
        preview_frame = tk.Frame(main_frame, bg="#2b2b2b")
        preview_frame.pack(fill="both", expand=True, pady=(0, 20))
        
        preview_label = tk.Label(
            preview_frame,
            text="📖 Szöveg előnézet:",
            font=tkfont.Font(size=14, weight="bold"),
            fg="white",
            bg="#2b2b2b",
            anchor="w"
        )
        preview_label.pack(fill="x", pady=(0, 5))
        
        # Szöveg terület scrollbar-ral
        text_frame = tk.Frame(preview_frame, bg="#2b2b2b")
        text_frame.pack(fill="both", expand=True)
        
        self.preview_text = tk.Text(
            text_frame,
            height=8,
            font=self.text_font,
            bg="#3c3c3c",
            fg="white",
            insertbackground="white",
            wrap="word",
            state="disabled"
        )
        
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=scrollbar.set)
        
        self.preview_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # API státusz
        api_frame = tk.Frame(main_frame, bg="#2b2b2b")
        api_frame.pack(fill="x", pady=(0, 20))
        
        api_label = tk.Label(
            api_frame,
            text="🔑 gTTS aktiválva - Hosszú szövegek támogatásával!",
            font=self.text_font,
            fg="#4CAF50",
            bg="#2b2b2b"
        )
        api_label.pack()
        
        # MOST JÖN A FÁJL BETÖLTŐ RÉSZ
        
        # Állapotjelző
        status_frame = tk.Frame(main_frame, bg="#2b2b2b")
        status_frame.pack(fill="x")
        
        self.status_label = tk.Label(
            status_frame,
            text="📄 Tölts be egy .txt fájlt a kezdéshez",
            font=self.text_font,
            fg="#4CAF50",
            bg="#2b2b2b"
        )
        self.status_label.pack(pady=15)
    
    def _split_text_into_chunks(self, text):
        """Szöveg darabolása mondatok mentén"""
        # Mondatok vége jelölők
        sentence_endings = r'[.!?]\s+'
        sentences = re.split(sentence_endings, text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if not sentence.strip():
                continue
                
            # Ha a jelenlegi chunk + új mondat túl hosszú
            if len(current_chunk) + len(sentence) + 2 > self.max_chunk_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    # Ha maga a mondat túl hosszú, daraboljuk fel
                    while len(sentence) > self.max_chunk_length:
                        chunks.append(sentence[:self.max_chunk_length])
                        sentence = sentence[self.max_chunk_length:]
                    current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += ". " + sentence
                else:
                    current_chunk = sentence
        
        # Utolsó chunk hozzáadása
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def update_progress(self, current, total, message=""):
        """Progress bar frissítése - NAGY LÁTHATÓ VERZIÓ"""
        print(f"🔄 Progress update: {current}/{total} - {message}")  # DEBUG
        
        if total > 0:
            percentage = (current / total) * 100
            self.progress_var.set(percentage)
            
            # Üzenet frissítés
            if message:
                progress_text = f"{message} ({current}/{total})"
            else:
                progress_text = f"Feldolgozás: {current}/{total} rész"
            
            # NAGY BETŰS FRISSÍTÉSEK
            self.progress_label.configure(text=progress_text, fg="#FF9800")
            self.progress_percent.configure(text=f"{percentage:.0f}%", fg="#4CAF50")
            
            self.root.update_idletasks()  # UI frissítés
            print(f"✅ Progress bar set to {percentage:.0f}%")  # DEBUG
    
    def update_status(self, message, status_type="info"):
        """Státusz frissítése színekkel"""
        colors = {
            "info": "#4CAF50",
            "working": "#FF9800", 
            "error": "#F44336",
            "success": "#2196F3"
        }
        
        icons = {
            "info": "ℹ️",
            "working": "⏳",
            "error": "❌",
            "success": "✅"
        }
        
        color = colors.get(status_type, "#4CAF50")
        icon = icons.get(status_type, "ℹ️")
        
        self.status_label.configure(text=f"{icon} {message}", fg=color)
        
        # Progress label is frissítése ha nincs aktív generálás
        if status_type in ["info", "success", "error"]:
            if "betöltve" in message:
                self.progress_label.configure(text="Kattints a 'OLVASD FEL' gombra!", fg="#4CAF50")
                self.progress_percent.configure(text="KÉSZ", fg="#4CAF50")
            elif "Hiba" in message:
                self.progress_label.configure(text="Hiba történt!", fg="#F44336")
                self.progress_percent.configure(text="❌", fg="#F44336")
        
    def show_progress(self, show=True):
        """Progress aktiválás/deaktiválás - már mindig látható!"""
        print(f"📊 Progress active: {show}")  # DEBUG
        
        if show:
            print("📊 Activating progress tracking...")  # DEBUG
            self.progress_label.configure(text="⏳ Készül a felolvasás...", fg="#FF9800")
            self.progress_percent.configure(text="0%", fg="#FF9800")
            self.progress_var.set(0)
            self.root.update_idletasks()  # Force UI update
            print("📊 Progress should be active now")  # DEBUG
        else:
            print("📊 Deactivating progress...")  # DEBUG
            self.progress_label.configure(text="🎉 Felolvasás kész!", fg="#4CAF50")
            self.progress_percent.configure(text="100%", fg="#4CAF50")
            self.progress_var.set(100)
    
    def load_file(self):
        """TXT fájl betöltése"""
        file_path = filedialog.askopenfilename(
            title="Szöveges fájl kiválasztása",
            filetypes=[("Szöveges fájlok", "*.txt"), ("Minden fájl", "*.*")]
        )
        if file_path:
            self.load_text_file(file_path)
    
    def load_text_file(self, file_path):
        """Szöveges fájl betöltése és megjelenítése"""
        try:
            # Különböző encodingok próbálása
            encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'iso-8859-1', 'cp1250']
            content = None
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                raise Exception("Nem sikerült dekódolni a fájlt")
            
            # Szöveg mentése
            self.current_text = content.strip()
            
            # UI frissítés
            filename = os.path.basename(file_path)
            self.file_icon_label.configure(text="📄✅")
            self.file_status_label.configure(
                text=f"Betöltve: {filename}\n{len(self.current_text)} karakter",
                fg="white"
            )
            
            # Előnézet frissítése
            self.preview_text.configure(state="normal")
            self.preview_text.delete("1.0", "end")
            
            # Első 500 karakter megjelenítése
            preview = self.current_text[:500]
            if len(self.current_text) > 500:
                preview += "\n\n... (továbbiak)"
            
            self.preview_text.insert("1.0", preview)
            self.preview_text.configure(state="disabled")
            
            # GOMBOK AKTIVÁLÁSA!!!
            if self.current_text.strip():
                self.generate_btn.configure(state="normal")
                self.read_aloud_btn.configure(state="normal")
                self.update_status("✅ Szöveg betöltve - Most már használhatod a gombokat!", "success")
            
        except Exception as e:
            messagebox.showerror("Hiba", f"Nem sikerült betölteni a fájlt:\n{str(e)}")
            self.update_status("Hiba a fájl betöltésekor", "error")
    
    def generate_audio(self):
        """Audio generálása HOSSZÚ SZÖVEGEKKEL"""
        if not self.current_text:
            messagebox.showerror("Hiba", "Nincs szöveg betöltve!")
            return
        
        # Szöveg darabolása
        text_chunks = self._split_text_into_chunks(self.current_text)
        self.total_chunks = len(text_chunks)
        
        if self.total_chunks > 1:
            if not messagebox.askyesno("Hosszú szöveg", 
                f"A szöveg {self.total_chunks} részre lesz bontva.\n"
                f"Minden rész külön audio fájl lesz.\nFolytatod?"):
                return
        
        # Generálás állapot beállítása
        self.generation_active = True
        self.stop_requested = False
        
        self.update_status(f"Audio generálása {self.total_chunks} részben...", "working")
        self.show_progress(True)
        self.generate_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")  # STOP aktiválása!
        
        # Chunks mentése és generálás indítása
        self.text_chunks = text_chunks
        self.audio_chunks = []
        
        threading.Thread(target=self._generate_audio_chunks_thread, daemon=True).start()
        
    def _generate_audio_chunks_thread(self):
        """Chunk-ok generálása egyenként progress bar-ral - STOP támogatással"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            for i, chunk in enumerate(self.text_chunks):
                # STOP ellenőrzés minden iterációnál
                if self.stop_requested:
                    print("🛑 Generálás leállítva felhasználói kérésre")
                    self.root.after(0, self._generation_stopped)
                    return
                
                # Progress frissítés - FIX: proper closure
                current_step = i + 1
                def update_progress_safe(step=current_step):
                    if not self.stop_requested:  # Csak ha nem állítottuk le
                        self.update_progress(step, self.total_chunks, f"Generálás {step}. rész")
                
                self.root.after(0, update_progress_safe)
                
                print(f"🎵 Generálás {i+1}/{self.total_chunks}: {chunk[:50]}...")
                
                # STOP ellenőrzés gTTS előtt is
                if self.stop_requested:
                    print("🛑 Generálás leállítva gTTS előtt")
                    self.root.after(0, self._generation_stopped)
                    return
                
                # gTTS generálás
                tts = gTTS(text=chunk, lang='hu', slow=False)
                
                # Fájlnév
                audio_filename = f"felolvasas_{timestamp}_part{i+1:03d}.mp3"
                audio_path = os.path.join(self.audio_dir, audio_filename)
                
                # Mentés
                tts.save(audio_path)
                self.audio_chunks.append(audio_path)
                
                print(f"✅ Kész: {audio_filename}")
                
                # Kis szünet hogy ne terhelje túl a Google szervert
                if i < len(self.text_chunks) - 1:  # Utolsó után nincs szünet
                    import time
                    time.sleep(1)
                    
                    # STOP ellenőrzés szünet után is
                    if self.stop_requested:
                        print("🛑 Generálás leállítva szünet után")
                        self.root.after(0, self._generation_stopped)
                        return
            
            # Ha idáig eljutottunk, sikeresen befejeződött
            if not self.stop_requested:
                # Első chunk beállítása lejátszáshoz
                self.current_audio_file = self.audio_chunks[0]
                self.current_chunk_index = 0
                
                self.root.after(0, self._audio_generated_successfully)
                
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self._audio_generation_failed(error_msg))
    
    def _audio_generated_successfully(self):
        """Audio generálás sikeres befejezése"""
        self.generation_active = False  # Generálás befejeződött
        
        if hasattr(self, 'audio_chunks') and len(self.audio_chunks) > 1:
            self.update_status(f"Audio sikeresen generálva! {len(self.audio_chunks)} rész 🎉", "success")
        else:
            self.update_status("Audio sikeresen generálva! 🎉", "success")
            
        self.show_progress(False)
        self.generate_btn.configure(state="normal")
        self.play_btn.configure(state="normal")
        self.save_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")  # STOP letiltása
        
    def _generation_stopped(self):
        """Generálás leállítás kezelése"""
        self.generation_active = False
        self.stop_requested = False
        
        self.update_status("🛑 Generálás leállítva", "error")
        self.show_progress(False)
        
        # Gombok visszaállítása
        self.generate_btn.configure(state="normal")
        self.read_aloud_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        
        # Ha van már generált chunk, azokat engedélyezzük
        if hasattr(self, 'audio_chunks') and self.audio_chunks:
            self.play_btn.configure(state="normal")
            self.save_btn.configure(state="normal")
            self.current_audio_file = self.audio_chunks[0]
            self.current_chunk_index = 0
            self.update_status(f"🛑 Leállítva - {len(self.audio_chunks)} rész már kész", "info")
        
    def _audio_generation_failed(self, error_msg):
        """Audio generálás hiba kezelése"""
        try:
            if self.root.winfo_exists():  # Ellenőrzi hogy létezik-e még az ablak
                messagebox.showerror("Hiba", f"Nem sikerült generálni az audiót:\n{error_msg}")
                self.update_status("Hiba az audio generálásakor", "error")
                self.show_progress(False)
                self.generate_btn.configure(state="normal")
        except tk.TclError:
            print(f"GUI destroyed, error was: {error_msg}")  # Terminálra kiírás
        
    def read_aloud(self):
        """Szöveg azonnali felolvasása HOSSZÚ SZÖVEGEKKEL"""
        if not self.current_text:
            messagebox.showerror("Hiba", "Nincs szöveg betöltve!")
            return
        
        # Szöveg darabolása
        text_chunks = self._split_text_into_chunks(self.current_text)
        self.total_chunks = len(text_chunks)
        
        if self.total_chunks > 10:
            if not messagebox.askyesno("Nagyon hosszú szöveg", 
                f"A szöveg {self.total_chunks} részre lesz bontva.\n"
                f"Ez eltarthat egy ideig.\nFolytatod?"):
                return
        
        # Generálás állapot beállítása
        self.generation_active = True
        self.stop_requested = False
        
        self.update_status(f"Felolvasás generálása {self.total_chunks} részben...", "working")
        self.show_progress(True)
        self.read_aloud_btn.configure(state="disabled")
        self.generate_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")  # STOP aktiválása!
        
        # Chunks mentése és generálás indítása
        self.text_chunks = text_chunks
        self.audio_chunks = []
        
        threading.Thread(target=self._read_aloud_chunks_thread, daemon=True).start()
        
    def _read_aloud_chunks_thread(self):
        """Read aloud chunk-ok generálása - STOP támogatással"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            for i, chunk in enumerate(self.text_chunks):
                # STOP ellenőrzés minden iterációnál
                if self.stop_requested:
                    print("🛑 Felolvasás generálás leállítva felhasználói kérésre")
                    self.root.after(0, self._generation_stopped)
                    return
                
                # Progress frissítés - FIX: proper closure
                current_step = i + 1
                def update_progress_safe(step=current_step):
                    if not self.stop_requested:  # Csak ha nem állítottuk le
                        self.update_progress(step, self.total_chunks, f"Generálás {step}. rész")
                
                self.root.after(0, update_progress_safe)
                
                print(f"🎵 Generálás {i+1}/{self.total_chunks}: {chunk[:50]}...")
                
                # STOP ellenőrzés gTTS előtt is
                if self.stop_requested:
                    print("🛑 Felolvasás generálás leállítva gTTS előtt")
                    self.root.after(0, self._generation_stopped)
                    return
                
                # gTTS generálás
                tts = gTTS(text=chunk, lang='hu', slow=False)
                
                # Fájlnév
                audio_filename = f"felolvasas_{timestamp}_part{i+1:03d}.mp3"
                audio_path = os.path.join(self.audio_dir, audio_filename)
                
                # Mentés
                tts.save(audio_path)
                self.audio_chunks.append(audio_path)
                
                print(f"✅ Kész: {audio_filename}")
                
                # Kis szünet
                if i < len(self.text_chunks) - 1:
                    import time
                    time.sleep(1)
                    
                    # STOP ellenőrzés szünet után is
                    if self.stop_requested:
                        print("🛑 Felolvasás generálás leállítva szünet után")
                        self.root.after(0, self._generation_stopped)
                        return
            
            # Ha idáig eljutottunk, sikeresen befejeződött
            if not self.stop_requested:
                # Első chunk beállítása és automatikus lejátszás
                self.current_audio_file = self.audio_chunks[0]
                self.current_chunk_index = 0
                
                self.root.after(0, self._read_aloud_success)
                
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self._read_aloud_failed(error_msg))
    
    def _read_aloud_success(self):
        """Azonnali felolvasás sikeres befejezése és AUTOMATIKUS lejátszás"""
        self.generation_active = False  # Generálás befejeződött
        
        self.show_progress(False)
        self.read_aloud_btn.configure(state="normal")
        self.generate_btn.configure(state="normal")
        self.play_btn.configure(state="normal")
        self.save_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")  # STOP marad aktív lejátszáshoz
        
        # Automatikus lejátszás indítása az első chunk-kal
        try:
            # Chunk index reset
            self.current_chunk_index = 0
            
            if hasattr(self, 'audio_chunks') and self.audio_chunks:
                total_chunks = len(self.audio_chunks)
                self.update_status(
                    f"Felolvasás indítása: 1/{total_chunks} rész 🔊", 
                    "working"
                )
            else:
                self.update_status("Felolvasás folyamatban... 🔊", "working")
            
            pygame.mixer.music.load(self.current_audio_file)
            pygame.mixer.music.play()
            self.is_playing = True
            self.play_btn.configure(state="disabled")
            # self.stop_btn.configure(state="normal")  # már aktív
            
            self._check_playback()
            
        except Exception as e:
            messagebox.showerror("Hiba", f"Nem sikerült lejátszani az audiót:\n{str(e)}")
            self.update_status("Audio generálva, de lejátszási hiba", "error")
            self.stop_btn.configure(state="disabled")
        
    def _read_aloud_failed(self, error_msg):
        """Azonnali felolvasás hiba kezelése"""
        try:
            if self.root.winfo_exists():  # Ellenőrzi hogy létezik-e még az ablak
                messagebox.showerror("Hiba", f"Nem sikerült felolvasni a szöveget:\n{error_msg}")
                self.update_status("Hiba a felolvasáskor", "error")
                self.show_progress(False)
                self.read_aloud_btn.configure(state="normal")
                self.generate_btn.configure(state="normal")
        except tk.TclError:
            print(f"GUI destroyed, error was: {error_msg}")  # Terminálra kiírás
        
    def play_audio(self):
        """Audio lejátszása (chunk-ok támogatásával)"""
        if not self.current_audio_file or not os.path.exists(self.current_audio_file):
            messagebox.showwarning("Nincs audio", "Nincs generált audio fájl!")
            return
            
        try:
            # Chunk index reset manuális lejátszásnál
            if hasattr(self, 'audio_chunks') and self.audio_chunks:
                self.current_chunk_index = 0
                self.current_audio_file = self.audio_chunks[0]
                
                # Multi-chunk státusz
                self.update_status(
                    f"Lejátszás: 1/{len(self.audio_chunks)} rész 🔊", 
                    "working"
                )
            else:
                self.update_status("Lejátszás folyamatban... 🔊", "working")
            
            pygame.mixer.music.load(self.current_audio_file)
            pygame.mixer.music.play()
            self.is_playing = True
            self.play_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")  # STOP aktiválása lejátszáshoz
            
            self._check_playback()
            
        except Exception as e:
            messagebox.showerror("Hiba", f"Nem sikerült lejátszani az audiót:\n{str(e)}")
        
    def _check_playback(self):
        """Lejátszás állapotának ellenőrzése + AUTOMATIKUS KÖVETKEZŐ CHUNK"""
        if pygame.mixer.music.get_busy():
            self.root.after(100, self._check_playback)
        else:
            if self.is_playing:
                # Ha van még chunk hátra, automatikusan lejátssza
                if (hasattr(self, 'audio_chunks') and 
                    self.current_chunk_index < len(self.audio_chunks) - 1):
                    
                    self.current_chunk_index += 1
                    next_chunk = self.audio_chunks[self.current_chunk_index]
                    
                    print(f"🎵 Következő rész: {self.current_chunk_index + 1}/{len(self.audio_chunks)}")
                    
                    try:
                        pygame.mixer.music.load(next_chunk)
                        pygame.mixer.music.play()
                        self.current_audio_file = next_chunk
                        
                        # Státusz frissítése
                        self.update_status(
                            f"Lejátszás: {self.current_chunk_index + 1}/{len(self.audio_chunks)} rész 🔊", 
                            "working"
                        )
                        
                        self.root.after(100, self._check_playback)  # Folytatjuk az ellenőrzést
                        return
                        
                    except Exception as e:
                        print(f"❌ Következő chunk lejátszási hiba: {e}")
                
                # Ha nincs több chunk vagy hiba volt - LEJÁTSZÁS VÉGE
                self.is_playing = False
                self.play_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")  # STOP letiltása
                
                if hasattr(self, 'audio_chunks') and len(self.audio_chunks) > 1:
                    self.update_status(f"Felolvasás befejezve! ({len(self.audio_chunks)} rész)", "success")
                else:
                    self.update_status("Lejátszás befejezve", "success")
        
    def stop_audio(self):
        """Audio lejátszás ÉS generálás megállítása - MINDENT LEÁLLÍT!"""
        print("🛑 STOP kérés - minden leállítása...")
        
        # 1. Generálás leállítása
        if self.generation_active:
            print("🛑 Generálás leállítása...")
            self.stop_requested = True
            self.generation_active = False
            
            # Progress reset
            self.progress_label.configure(text="❌ Leállítva!", fg="#F44336")
            self.progress_percent.configure(text="STOP", fg="#F44336")
            self.show_progress(False)
            
            # Gombok visszaállítása
            self.read_aloud_btn.configure(state="normal")
            self.generate_btn.configure(state="normal")
        
        # 2. Lejátszás leállítása
        if self.is_playing:
            print("🛑 Lejátszás leállítása...")
            pygame.mixer.music.stop()
            self.is_playing = False
            self.play_btn.configure(state="normal")
        
        # 3. UI frissítés
        self.stop_btn.configure(state="disabled")
        self.update_status("🛑 Minden leállítva", "error")
        
        print("✅ Minden leállítva!")
    
    def save_audio(self):
        """Audio mentése fájlba"""
        if self.current_audio_file and os.path.exists(self.current_audio_file):
            # Alapértelmezett fájlnév timestamppel
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") 
            default_name = f"felolvasas_{timestamp}.mp3"
            
            file_path = filedialog.asksaveasfilename(
                title="Audio mentése",
                defaultextension=".mp3",
                initialfilename=default_name,
                filetypes=[("MP3 fájlok", "*.mp3"), ("Minden fájl", "*.*")]
            )
            if file_path:
                try:
                    with open(self.current_audio_file, 'rb') as src:
                        with open(file_path, 'wb') as dst:
                            dst.write(src.read())
                    messagebox.showinfo("Siker", f"Audio sikeresen mentve:\n{file_path}")
                    self.update_status("Audio sikeresen mentve! 💾", "success")
                except Exception as e:
                    messagebox.showerror("Hiba", f"Nem sikerült menteni az audiót:\n{str(e)}")
        else:
            # Ha nincs audio, mutassa hol vannak az automatikus mentések
            messagebox.showinfo("Info", f"Az audio fájlok automatikusan mentve vannak itt:\n{self.audio_dir}")
    
    def run(self):
        """Alkalmazás indítása"""
        self.root.mainloop()

def main():
    app = FaternakFelolvasoProgram()
    app.run()

if __name__ == "__main__":
    main()
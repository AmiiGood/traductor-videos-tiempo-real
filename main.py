import pyaudio
import speech_recognition as sr
import tkinter as tk
from tkinter import ttk
import threading
import queue
import time
import numpy as np
from deep_translator import GoogleTranslator
from collections import deque

class GoogleVideoTranslator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Traductor de Videos - Google Translate")
        self.root.geometry("900x400")
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.95)
        
        # Configuracion de audio
        self.CHUNK = 512
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 2
        self.RATE = 16000
        
        # Reconocedor
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.5
        self.recognizer.phrase_threshold = 0.1
        
        # Traductores
        self.translators = {}
        
        # Colas y buffers
        self.audio_queue = queue.Queue(maxsize=10)
        self.translation_cache = {}
        
        # Variables de control
        self.is_running = False
        self.device_index = 1
        
        # Estadisticas
        self.translations_count = 0
        self.start_time = None
        
        self.setup_ui()
        
    def setup_ui(self):
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Panel de control
        control_panel = ttk.LabelFrame(main_frame, text="Panel de Control", padding="10")
        control_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Primera fila
        row1 = ttk.Frame(control_panel)
        row1.pack(fill=tk.X, pady=2)
        
        self.start_button = ttk.Button(row1, text="▶ Iniciar", command=self.toggle_translation, width=15)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Estado con indicador visual
        self.status_frame = ttk.Frame(row1)
        self.status_frame.pack(side=tk.LEFT, padx=10)
        
        self.status_indicator = tk.Canvas(self.status_frame, width=20, height=20)
        self.status_indicator.pack(side=tk.LEFT)
        self.status_circle = self.status_indicator.create_oval(2, 2, 18, 18, fill="red")
        
        self.status_label = ttk.Label(self.status_frame, text="Detenido")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # Dispositivo
        ttk.Label(row1, text="Dispositivo:").pack(side=tk.LEFT, padx=(20, 5))
        self.device_var = tk.StringVar(value="1")
        device_spin = ttk.Spinbox(row1, from_=0, to=30, textvariable=self.device_var, width=5)
        device_spin.pack(side=tk.LEFT)
        
        # Segunda fila - Idiomas
        row2 = ttk.Frame(control_panel)
        row2.pack(fill=tk.X, pady=5)
        
        # Idiomas con banderas (emoji)
        ttk.Label(row2, text="Idioma origen:").pack(side=tk.LEFT, padx=5)
        self.source_lang = tk.StringVar(value='en')
        source_combo = ttk.Combobox(row2, textvariable=self.source_lang, width=20)
        source_combo['values'] = (
            'auto',
            'en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh-cn', 'zh-tw',
            'ar', 'hi', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi'
        )
        source_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="Traducir a:").pack(side=tk.LEFT, padx=(20, 5))
        self.target_lang = tk.StringVar(value='es')
        target_combo = ttk.Combobox(row2, textvariable=self.target_lang, width=20)
        target_combo['values'] = (
            'es', 'en', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh-cn', 'zh-tw',
            'ar', 'hi', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi'
        )
        target_combo.pack(side=tk.LEFT, padx=5)
        
        # Tercera fila - Opciones
        row3 = ttk.Frame(control_panel)
        row3.pack(fill=tk.X, pady=2)
        
        # Opciones
        self.auto_detect = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="Deteccion automatica de idioma", 
                       variable=self.auto_detect,
                       command=self.toggle_auto_detect).pack(side=tk.LEFT, padx=5)
        
        # Sensibilidad
        ttk.Label(row3, text="Sensibilidad:").pack(side=tk.LEFT, padx=(20, 5))
        self.sensitivity = tk.IntVar(value=300)
        sensitivity_scale = ttk.Scale(row3, from_=100, to=1000, variable=self.sensitivity,
                                    orient=tk.HORIZONTAL, length=150,
                                    command=self.update_sensitivity)
        sensitivity_scale.pack(side=tk.LEFT)
        
        self.sensitivity_label = ttk.Label(row3, text="300")
        self.sensitivity_label.pack(side=tk.LEFT, padx=5)
        
        # Monitor de audio
        audio_frame = ttk.LabelFrame(main_frame, text="Monitor de Audio", padding="5")
        audio_frame.pack(fill=tk.X, pady=5)
        
        self.audio_canvas = tk.Canvas(audio_frame, height=40, bg='black')
        self.audio_canvas.pack(fill=tk.X)
        
        # Crear barras del visualizador
        self.audio_bars = []
        for i in range(50):
            bar = self.audio_canvas.create_rectangle(
                i * 18, 40, i * 18 + 15, 40,
                fill='green', outline=''
            )
            self.audio_bars.append(bar)
        
        # area de subtitulos mejorada
        subtitle_frame = ttk.LabelFrame(main_frame, text="Subtitulos en Tiempo Real", padding="5")
        subtitle_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas para efecto de subtitulos profesional
        self.subtitle_canvas = tk.Canvas(subtitle_frame, bg='black', height=120)
        self.subtitle_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Textos con sombra
        self.shadow_text = self.subtitle_canvas.create_text(
            452, 52,
            text="",
            font=('Arial', 20, 'bold'),
            fill='black',
            anchor='center',
            width=850
        )
        
        self.main_text = self.subtitle_canvas.create_text(
            450, 50,
            text="",
            font=('Arial', 20, 'bold'),
            fill='yellow',
            anchor='center',
            width=850
        )
        
        self.original_text = self.subtitle_canvas.create_text(
            450, 85,
            text="",
            font=('Arial', 14),
            fill='white',
            anchor='center',
            width=850
        )
        
        # Panel de estadisticas
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.stats_label = ttk.Label(stats_frame, text="Traducciones: 0 | Tiempo: 00:00")
        self.stats_label.pack(side=tk.LEFT)
        
        # Calidad de conexion
        self.connection_label = ttk.Label(stats_frame, text="🟢 Conexion OK", foreground="green")
        self.connection_label.pack(side=tk.RIGHT, padx=10)
        
    def toggle_auto_detect(self):
        if self.auto_detect.get():
            self.source_lang.set('auto')
            
    def update_sensitivity(self, value):
        self.sensitivity_label.config(text=str(int(float(value))))
        if hasattr(self, 'recognizer'):
            self.recognizer.energy_threshold = int(float(value))
            
    def get_translator(self, source, target):
        key = f"{source}_{target}"
        if key not in self.translators:
            if source == 'auto':
                self.translators[key] = GoogleTranslator(source='auto', target=target)
            else:
                self.translators[key] = GoogleTranslator(source=source, target=target)
        return self.translators[key]
        
    def toggle_translation(self):
        if not self.is_running:
            self.start_translation()
        else:
            self.stop_translation()
            
    def start_translation(self):
        self.is_running = True
        self.start_button.config(text="⏸ Detener")
        self.status_indicator.itemconfig(self.status_circle, fill="green")
        self.status_label.config(text="Escuchando...")
        
        self.device_index = int(self.device_var.get())
        self.recognizer.energy_threshold = self.sensitivity.get()
        
        # Reset estadisticas
        self.translations_count = 0
        self.start_time = time.time()
        
        # Limpiar subtitulos
        self.clear_subtitles()
        
        # Iniciar threads
        self.audio_thread = threading.Thread(target=self.capture_audio, daemon=True)
        self.audio_thread.start()
        
        self.stats_thread = threading.Thread(target=self.update_stats, daemon=True)
        self.stats_thread.start()
        
    def stop_translation(self):
        self.is_running = False
        self.start_button.config(text="▶ Iniciar")
        self.status_indicator.itemconfig(self.status_circle, fill="red")
        self.status_label.config(text="Detenido")
        
    def capture_audio(self):
        try:
            p = pyaudio.PyAudio()
            
            stream = p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=self.CHUNK
            )
            
            print(f"Capturando desde dispositivo {self.device_index}")
            
            # Usar reconocimiento con microfono para mejor integracion
            with sr.Microphone(device_index=self.device_index, sample_rate=self.RATE) as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                print("Ajuste completado, escuchando...")
                
                while self.is_running:
                    try:
                        # Actualizar visualizador
                        data = stream.read(self.CHUNK, exception_on_overflow=False)
                        self.update_visualizer(data)
                        
                        # Escuchar audio
                        audio = self.recognizer.listen(source, timeout=0.5, phrase_time_limit=5)
                        
                        # Procesar en thread separado
                        threading.Thread(
                            target=self.process_audio,
                            args=(audio,),
                            daemon=True
                        ).start()
                        
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        print(f"Error en captura: {e}")
                        
            stream.stop_stream()
            stream.close()
            p.terminate()
            
        except Exception as e:
            print(f"Error iniciando captura: {e}")
            self.connection_label.config(text="🔴 Error de audio", foreground="red")
            self.stop_translation()
            
    def update_visualizer(self, data):
        try:
            # Convertir a array numpy
            audio_array = np.frombuffer(data, dtype=np.int16)
            
            # Calcular FFT para frecuencias
            fft = np.abs(np.fft.rfft(audio_array))
            fft = fft[:50]  # Tomar solo 50 bandas
            
            # Normalizar
            if fft.max() > 0:
                fft = fft / fft.max() * 35
            
            # Actualizar barras
            for i, bar in enumerate(self.audio_bars):
                if i < len(fft):
                    height = int(fft[i])
                    self.audio_canvas.coords(bar, i * 18, 40 - height, i * 18 + 15, 40)
                    
                    # Color segun intensidad
                    if height > 25:
                        color = '#ff0000'
                    elif height > 15:
                        color = '#ffff00'
                    else:
                        color = '#00ff00'
                    self.audio_canvas.itemconfig(bar, fill=color)
                    
        except Exception as e:
            pass
            
    def process_audio(self, audio):
        try:
            start_time = time.time()
            
            # Reconocimiento de voz
            if self.source_lang.get() == 'auto':
                # Intentar detectar idioma
                text = self.recognizer.recognize_google(audio, show_all=False)
            else:
                # Usar idioma especificado
                lang_code = self.source_lang.get()
                # Mapear codigos cortos a codigos completos para speech recognition
                lang_map = {
                    'en': 'en-US', 'es': 'es-ES', 'fr': 'fr-FR',
                    'de': 'de-DE', 'it': 'it-IT', 'pt': 'pt-BR',
                    'ru': 'ru-RU', 'ja': 'ja-JP', 'ko': 'ko-KR',
                    'zh-cn': 'zh-CN', 'ar': 'ar-SA', 'hi': 'hi-IN'
                }
                speech_lang = lang_map.get(lang_code, lang_code)
                text = self.recognizer.recognize_google(audio, language=speech_lang)
            
            if text:
                print(f"Reconocido: {text}")
                
                # Verificar cache
                cache_key = f"{text}_{self.target_lang.get()}"
                if cache_key in self.translation_cache:
                    translation = self.translation_cache[cache_key]
                    print("(desde cache)")
                else:
                    # Traducir con Google
                    translator = self.get_translator(self.source_lang.get(), self.target_lang.get())
                    translation = translator.translate(text)
                    
                    # Guardar en cache
                    self.translation_cache[cache_key] = translation
                    
                    # Limpiar cache si es muy grande
                    if len(self.translation_cache) > 100:
                        self.translation_cache.clear()
                
                # Calcular tiempo de procesamiento
                process_time = time.time() - start_time
                print(f"Traducido en {process_time:.2f}s: {translation}")
                
                # Actualizar UI
                self.update_subtitles(text, translation)
                
                # Actualizar estadisticas
                self.translations_count += 1
                
                # Actualizar indicador de conexion
                if process_time < 1:
                    self.connection_label.config(text="🟢 Conexion excelente", foreground="green")
                elif process_time < 2:
                    self.connection_label.config(text="🟡 Conexion buena", foreground="orange")
                else:
                    self.connection_label.config(text="🔴 Conexion lenta", foreground="red")
                    
        except sr.UnknownValueError:
            pass  # Audio no reconocido
        except sr.RequestError as e:
            print(f"Error con servicio de reconocimiento: {e}")
            self.connection_label.config(text="🔴 Error de servicio", foreground="red")
        except Exception as e:
            print(f"Error en traduccion: {e}")
            self.connection_label.config(text="🔴 Error", foreground="red")
            
    def update_subtitles(self, original, translation):
        def update():
            # Actualizar textos
            self.subtitle_canvas.itemconfig(self.shadow_text, text=translation)
            self.subtitle_canvas.itemconfig(self.main_text, text=translation)
            self.subtitle_canvas.itemconfig(self.original_text, text=f"({original})")
            
            # Efecto de aparicion
            self.subtitle_canvas.itemconfig(self.main_text, fill='white')
            self.root.after(50, lambda: self.subtitle_canvas.itemconfig(self.main_text, fill='yellow'))
            
            # Limpiar despues de 4 segundos
            self.root.after(4000, self.clear_subtitles)
            
        self.root.after(0, update)
        
    def clear_subtitles(self):
        if not self.is_running:
            self.subtitle_canvas.itemconfig(self.main_text, text="")
            self.subtitle_canvas.itemconfig(self.shadow_text, text="")
            self.subtitle_canvas.itemconfig(self.original_text, text="")
            
    def update_stats(self):
        while self.is_running:
            if self.start_time:
                elapsed = int(time.time() - self.start_time)
                minutes = elapsed // 60
                seconds = elapsed % 60
                
                self.stats_label.config(
                    text=f"Traducciones: {self.translations_count} | Tiempo: {minutes:02d}:{seconds:02d}"
                )
            
            time.sleep(1)
            
    def run(self):
        # Centrar ventana en la parte inferior
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = self.root.winfo_screenheight() - self.root.winfo_height() - 100
        self.root.geometry(f"+{x}+{y}")
        
        print("=== TRADUCTOR CON GOOGLE TRANSLATE ===")
        print("Caracteristicas:")
        print("- Usa Google Translate real")
        print("- Deteccion automatica de idioma")
        print("- Soporte para 20+ idiomas")
        print("- Visualizador de audio")
        print("- Cache de traducciones")
        
        self.root.mainloop()

if __name__ == "__main__":
    app = GoogleVideoTranslator()
    app.run()
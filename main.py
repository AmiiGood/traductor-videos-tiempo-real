import pyaudio
import speech_recognition as sr
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import time
import numpy as np
from deep_translator import GoogleTranslator
from collections import deque
import sys

class AudioDiagnosticTranslator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Traductor con Diagnóstico de Audio")
        self.root.geometry("950x600")
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.95)
        
        # Configuracion de audio
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000
        
        # PyAudio
        self.p = pyaudio.PyAudio()
        
        # Reconocedor
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.pause_threshold = 0.8
        self.recognizer.dynamic_energy_threshold = True
        
        # Traductores
        self.translators = {}
        
        # Variables de control
        self.is_running = False
        self.device_index = None
        self.stream = None
        
        # Estadisticas
        self.audio_level_history = deque(maxlen=100)
        self.translations_count = 0
        
        # Cola para procesamiento
        self.audio_queue = queue.Queue()
        
        self.setup_ui()
        self.detect_audio_devices()
        
    def setup_ui(self):
        # Notebook para pestañas
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Pestaña principal
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text="Traductor")
        
        # Pestaña de diagnostico
        diag_tab = ttk.Frame(notebook)
        notebook.add(diag_tab, text="Diagnóstico")
        
        # === PESTAÑA PRINCIPAL ===
        # Panel de control
        control_panel = ttk.LabelFrame(main_tab, text="Panel de Control", padding="10")
        control_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Primera fila - Control principal
        row1 = ttk.Frame(control_panel)
        row1.pack(fill=tk.X, pady=2)
        
        self.start_button = ttk.Button(row1, text="▶ Iniciar", command=self.toggle_translation, width=15)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # Estado
        self.status_label = ttk.Label(row1, text="Estado: Detenido", font=('Arial', 10, 'bold'))
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # Selector de dispositivo
        ttk.Label(row1, text="Dispositivo:").pack(side=tk.LEFT, padx=(20, 5))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(row1, textvariable=self.device_var, width=40, state='readonly')
        self.device_combo.pack(side=tk.LEFT, padx=5)
        self.device_combo.bind('<<ComboboxSelected>>', self.on_device_change)
        
        # Boton de refrescar dispositivos
        ttk.Button(row1, text="🔄", command=self.detect_audio_devices, width=3).pack(side=tk.LEFT)
        
        # Segunda fila - Idiomas
        row2 = ttk.Frame(control_panel)
        row2.pack(fill=tk.X, pady=5)
        
        ttk.Label(row2, text="Idioma origen:").pack(side=tk.LEFT, padx=5)
        self.source_lang = tk.StringVar(value='en')
        source_combo = ttk.Combobox(row2, textvariable=self.source_lang, width=15)
        source_combo['values'] = ('auto', 'en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'zh-TW')
        source_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="Traducir a:").pack(side=tk.LEFT, padx=(20, 5))
        self.target_lang = tk.StringVar(value='es')
        target_combo = ttk.Combobox(row2, textvariable=self.target_lang, width=15)
        target_combo['values'] = ('es', 'en', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'zh-TW')
        target_combo.pack(side=tk.LEFT, padx=5)
        
        # Sensibilidad
        ttk.Label(row2, text="Sensibilidad:").pack(side=tk.LEFT, padx=(20, 5))
        self.sensitivity = tk.IntVar(value=300)
        sensitivity_scale = ttk.Scale(row2, from_=100, to=2000, variable=self.sensitivity,
                                    orient=tk.HORIZONTAL, length=150)
        sensitivity_scale.pack(side=tk.LEFT)
        self.sensitivity_label = ttk.Label(row2, text="300")
        self.sensitivity_label.pack(side=tk.LEFT, padx=5)
        sensitivity_scale.config(command=lambda v: self.sensitivity_label.config(text=str(int(float(v)))))
        
        # Monitor de audio
        audio_frame = ttk.LabelFrame(main_tab, text="Monitor de Audio", padding="5")
        audio_frame.pack(fill=tk.X, pady=5)
        
        # Nivel de audio
        self.audio_level_frame = ttk.Frame(audio_frame)
        self.audio_level_frame.pack(fill=tk.X)
        
        ttk.Label(self.audio_level_frame, text="Nivel:").pack(side=tk.LEFT, padx=5)
        self.level_bar = ttk.Progressbar(self.audio_level_frame, length=300, mode='determinate')
        self.level_bar.pack(side=tk.LEFT, padx=5)
        
        self.level_label = ttk.Label(self.audio_level_frame, text="0 dB")
        self.level_label.pack(side=tk.LEFT, padx=5)
        
        self.speaking_indicator = ttk.Label(self.audio_level_frame, text="🔇", font=('Arial', 20))
        self.speaking_indicator.pack(side=tk.LEFT, padx=20)
        
        # Area de subtitulos
        subtitle_frame = ttk.LabelFrame(main_tab, text="Subtítulos", padding="5")
        subtitle_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Canvas para subtitulos
        self.subtitle_canvas = tk.Canvas(subtitle_frame, bg='black', height=120)
        self.subtitle_canvas.pack(fill=tk.BOTH, expand=True)
        
        self.main_text = self.subtitle_canvas.create_text(
            475, 40,
            text="Esperando audio...",
            font=('Arial', 24, 'bold'),
            fill='yellow',
            anchor='center',
            width=900
        )
        
        self.original_text = self.subtitle_canvas.create_text(
            475, 80,
            text="",
            font=('Arial', 16),
            fill='white',
            anchor='center',
            width=900
        )
        
        # === PESTAÑA DE DIAGNÓSTICO ===
        # Informacion del sistema
        info_frame = ttk.LabelFrame(diag_tab, text="Información del Sistema", padding="10")
        info_frame.pack(fill=tk.X, pady=5)
        
        self.info_text = tk.Text(info_frame, height=8, width=80)
        self.info_text.pack(fill=tk.X)
        
        # Log de depuracion
        log_frame = ttk.LabelFrame(diag_tab, text="Log de Depuración", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Botones de prueba
        test_frame = ttk.Frame(diag_tab)
        test_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(test_frame, text="Probar Dispositivo", command=self.test_device).pack(side=tk.LEFT, padx=5)
        ttk.Button(test_frame, text="Probar Reconocimiento", command=self.test_recognition).pack(side=tk.LEFT, padx=5)
        ttk.Button(test_frame, text="Limpiar Log", command=lambda: self.log_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=5)
        
        # Redirigir stdout al log
        sys.stdout = self.StdoutRedirector(self.log_text)
        
    def detect_audio_devices(self):
        """Detectar dispositivos de audio disponibles"""
        self.log("=== Detectando dispositivos de audio ===")
        
        devices = []
        device_map = {}
        
        # Obtener informacion del host
        host_info = self.p.get_default_host_api_info()
        self.log(f"API de audio: {host_info['name']}")
        
        # Listar dispositivos
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:  # Solo dispositivos de entrada
                    name = f"{i}: {info['name']} ({info['maxInputChannels']}ch)"
                    devices.append(name)
                    device_map[name] = i
                    
                    # Log detallado
                    self.log(f"\nDispositivo {i}:")
                    self.log(f"  Nombre: {info['name']}")
                    self.log(f"  Canales: {info['maxInputChannels']}")
                    self.log(f"  Rate: {info['defaultSampleRate']} Hz")
                    
                    # Marcar dispositivo predeterminado
                    if i == host_info['defaultInputDevice']:
                        self.log("  *** DISPOSITIVO PREDETERMINADO ***")
                        
            except Exception as e:
                self.log(f"Error en dispositivo {i}: {e}")
        
        # Actualizar combo
        self.device_combo['values'] = devices
        if devices:
            # Seleccionar dispositivo predeterminado
            default_device = host_info.get('defaultInputDevice', 0)
            for name, idx in device_map.items():
                if idx == default_device:
                    self.device_combo.set(name)
                    break
            else:
                self.device_combo.current(0)
                
        self.device_map = device_map
        
        # Actualizar info
        self.update_system_info()
        
    def update_system_info(self):
        """Actualizar informacion del sistema"""
        self.info_text.delete(1.0, tk.END)
        
        info = []
        info.append(f"Python: {sys.version.split()[0]}")
        info.append(f"PyAudio: {pyaudio.get_portaudio_version_text()}")
        info.append(f"Speech Recognition: {sr.__version__}")
        info.append(f"Dispositivos de entrada detectados: {len(self.device_map)}")
        
        if hasattr(self, 'device_map') and self.device_combo.get():
            device_idx = self.device_map.get(self.device_combo.get())
            if device_idx is not None:
                device_info = self.p.get_device_info_by_index(device_idx)
                info.append(f"\nDispositivo seleccionado:")
                info.append(f"  Índice: {device_idx}")
                info.append(f"  Nombre: {device_info['name']}")
                info.append(f"  Sample Rate: {device_info['defaultSampleRate']} Hz")
                
        self.info_text.insert(1.0, '\n'.join(info))
        
    def on_device_change(self, event=None):
        """Cambio de dispositivo"""
        if hasattr(self, 'device_map') and self.device_combo.get():
            self.device_index = self.device_map.get(self.device_combo.get())
            self.log(f"Dispositivo cambiado a: {self.device_combo.get()}")
            self.update_system_info()
            
    def test_device(self):
        """Probar dispositivo de audio"""
        if not hasattr(self, 'device_map') or not self.device_combo.get():
            self.log("ERROR: No hay dispositivo seleccionado")
            return
            
        self.log("\n=== Prueba de dispositivo ===")
        device_idx = self.device_map.get(self.device_combo.get())
        
        try:
            # Abrir stream temporal
            stream = self.p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                input_device_index=device_idx,
                frames_per_buffer=self.CHUNK
            )
            
            self.log("✓ Stream abierto exitosamente")
            self.log("Capturando 3 segundos de audio...")
            
            # Capturar audio
            frames = []
            max_level = 0
            
            for i in range(0, int(self.RATE / self.CHUNK * 3)):
                data = stream.read(self.CHUNK)
                frames.append(data)
                
                # Calcular nivel
                audio_data = np.frombuffer(data, dtype=np.int16)
                level = np.max(np.abs(audio_data))
                max_level = max(max_level, level)
                
                # Actualizar barra
                self.level_bar['value'] = (level / 32768) * 100
                self.root.update()
                
            stream.stop_stream()
            stream.close()
            
            self.log(f"✓ Captura completa")
            self.log(f"  Nivel máximo: {max_level} ({(max_level/32768)*100:.1f}%)")
            
            if max_level < 100:
                self.log("⚠️ ADVERTENCIA: Nivel muy bajo, verifica el micrófono")
            else:
                self.log("✓ Niveles de audio OK")
                
        except Exception as e:
            self.log(f"❌ ERROR: {e}")
            
    def test_recognition(self):
        """Probar reconocimiento de voz"""
        if not hasattr(self, 'device_map') or not self.device_combo.get():
            self.log("ERROR: No hay dispositivo seleccionado")
            return
            
        self.log("\n=== Prueba de reconocimiento ===")
        device_idx = self.device_map.get(self.device_combo.get())
        
        try:
            # Usar microfono
            with sr.Microphone(device_index=device_idx, sample_rate=self.RATE) as source:
                self.log("Ajustando para ruido ambiente...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.log(f"Umbral de energía: {self.recognizer.energy_threshold}")
                
                self.log("\n🎤 HABLA AHORA (5 segundos)...")
                self.subtitle_canvas.itemconfig(self.main_text, text="🎤 HABLA AHORA...", fill='red')
                
                try:
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    self.log("✓ Audio capturado, procesando...")
                    
                    # Reconocer
                    lang_code = 'es-ES' if self.source_lang.get() == 'es' else 'en-US'
                    text = self.recognizer.recognize_google(audio, language=lang_code)
                    
                    self.log(f"✓ RECONOCIDO: '{text}'")
                    self.subtitle_canvas.itemconfig(self.main_text, text=text, fill='green')
                    
                    # Probar traduccion
                    if text:
                        translator = GoogleTranslator(source='auto', target=self.target_lang.get())
                        translation = translator.translate(text)
                        self.log(f"✓ TRADUCIDO: '{translation}'")
                        self.subtitle_canvas.itemconfig(self.original_text, text=f"Traducción: {translation}")
                        
                except sr.WaitTimeoutError:
                    self.log("❌ Tiempo agotado - no se detectó habla")
                except sr.UnknownValueError:
                    self.log("❌ No se pudo entender el audio")
                except Exception as e:
                    self.log(f"❌ Error: {e}")
                    
        except Exception as e:
            self.log(f"❌ Error al abrir micrófono: {e}")
            
    def toggle_translation(self):
        if not self.is_running:
            self.start_translation()
        else:
            self.stop_translation()
            
    def start_translation(self):
        """Iniciar traduccion"""
        if not hasattr(self, 'device_map') or not self.device_combo.get():
            self.log("ERROR: Selecciona un dispositivo primero")
            return
            
        self.is_running = True
        self.start_button.config(text="⏸ Detener")
        self.status_label.config(text="Estado: Escuchando...", foreground="green")
        
        # Limpiar
        self.subtitle_canvas.itemconfig(self.main_text, text="Escuchando...", fill='yellow')
        self.subtitle_canvas.itemconfig(self.original_text, text="")
        
        # Obtener dispositivo
        self.device_index = self.device_map.get(self.device_combo.get())
        
        # Actualizar sensibilidad
        self.recognizer.energy_threshold = self.sensitivity.get()
        
        # Iniciar threads
        self.capture_thread = threading.Thread(target=self.capture_audio, daemon=True)
        self.capture_thread.start()
        
        self.process_thread = threading.Thread(target=self.process_audio, daemon=True)
        self.process_thread.start()
        
        self.monitor_thread = threading.Thread(target=self.monitor_levels, daemon=True)
        self.monitor_thread.start()
        
        self.log("\n=== Traducción iniciada ===")
        
    def stop_translation(self):
        """Detener traduccion"""
        self.is_running = False
        self.start_button.config(text="▶ Iniciar")
        self.status_label.config(text="Estado: Detenido", foreground="red")
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
                
        self.log("\n=== Traducción detenida ===")
        
    def capture_audio(self):
        """Capturar audio continuamente"""
        try:
            with sr.Microphone(device_index=self.device_index, sample_rate=self.RATE) as source:
                self.log(f"Micrófono abierto en dispositivo {self.device_index}")
                
                # Ajustar para ruido
                self.log("Ajustando para ruido ambiente...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                self.log(f"Umbral inicial: {self.recognizer.energy_threshold}")
                
                while self.is_running:
                    try:
                        # Escuchar con timeout corto
                        self.log("Esperando habla...")
                        audio = self.recognizer.listen(source, timeout=0.5, phrase_time_limit=5)
                        
                        # Añadir a cola
                        self.audio_queue.put(audio)
                        self.log("Audio capturado y añadido a cola")
                        
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        self.log(f"Error en captura: {e}")
                        
        except Exception as e:
            self.log(f"Error fatal en captura: {e}")
            self.stop_translation()
            
    def process_audio(self):
        """Procesar audio de la cola"""
        while self.is_running:
            try:
                # Obtener audio
                audio = self.audio_queue.get(timeout=1)
                
                self.log("Procesando audio...")
                
                # Reconocer
                try:
                    # Determinar idioma
                    if self.source_lang.get() == 'auto':
                        text = self.recognizer.recognize_google(audio)
                    else:
                        lang_map = {
                            'en': 'en-US', 'es': 'es-ES', 'fr': 'fr-FR',
                            'de': 'de-DE', 'it': 'it-IT', 'pt': 'pt-BR',
                            'ja': 'ja-JP', 'ko': 'ko-KR', 'zh-TW': 'zh-TW'
                        }
                        lang_code = lang_map.get(self.source_lang.get(), 'en-US')
                        text = self.recognizer.recognize_google(audio, language=lang_code)
                    
                    if text:
                        self.log(f"RECONOCIDO: '{text}'")
                        
                        # Mostrar texto original
                        self.subtitle_canvas.itemconfig(self.original_text, text=f"Original: {text}", fill='white')
                        
                        # Traducir
                        translator = self.get_translator(self.source_lang.get(), self.target_lang.get())
                        translation = translator.translate(text)
                        
                        self.log(f"TRADUCIDO: '{translation}'")
                        
                        # Mostrar traduccion
                        self.subtitle_canvas.itemconfig(self.main_text, text=translation, fill='yellow')
                        
                        self.translations_count += 1
                        
                        # Limpiar después de 4 segundos
                        threading.Timer(4.0, self.clear_subtitles).start()
                        
                except sr.UnknownValueError:
                    self.log("No se pudo entender el audio")
                except sr.RequestError as e:
                    self.log(f"Error con Google: {e}")
                except Exception as e:
                    self.log(f"Error en procesamiento: {e}")
                    
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Error: {e}")
                
    def monitor_levels(self):
        """Monitorear niveles de audio"""
        try:
            stream = self.p.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=256  # Pequeño para actualizacion rapida
            )
            
            while self.is_running:
                try:
                    data = stream.read(256, exception_on_overflow=False)
                    
                    # Calcular nivel
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    level = np.sqrt(np.mean(audio_data**2))
                    
                    # Actualizar UI
                    normalized_level = min(100, (level / 5000) * 100)
                    self.level_bar['value'] = normalized_level
                    
                    # Actualizar etiqueta
                    db = 20 * np.log10(max(1, level))
                    self.level_label.config(text=f"{db:.1f} dB")
                    
                    # Indicador de habla
                    if level > self.sensitivity.get():
                        self.speaking_indicator.config(text="🎤", foreground="red")
                    else:
                        self.speaking_indicator.config(text="🔇", foreground="gray")
                        
                except Exception:
                    pass
                    
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            self.log(f"Error en monitor: {e}")
            
    def get_translator(self, source, target):
        """Obtener traductor"""
        key = f"{source}_{target}"
        if key not in self.translators:
            if source == 'auto':
                self.translators[key] = GoogleTranslator(source='auto', target=target)
            else:
                self.translators[key] = GoogleTranslator(source=source, target=target)
        return self.translators[key]
        
    def clear_subtitles(self):
        """Limpiar subtitulos"""
        if not self.is_running:
            self.subtitle_canvas.itemconfig(self.main_text, text="")
            self.subtitle_canvas.itemconfig(self.original_text, text="")
            
    def log(self, message):
        """Añadir mensaje al log"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    class StdoutRedirector:
        """Redirigir stdout al widget de texto"""
        def __init__(self, text_widget):
            self.text_widget = text_widget
            
        def write(self, string):
            self.text_widget.insert(tk.END, string)
            self.text_widget.see(tk.END)
            self.text_widget.update()
            
        def flush(self):
            pass
            
    def run(self):
        self.log("=== TRADUCTOR CON DIAGNÓSTICO ===")
        self.log("1. Selecciona tu dispositivo de audio")
        self.log("2. Usa la pestaña 'Diagnóstico' para probar")
        self.log("3. Ajusta la sensibilidad si es necesario")
        self.log("4. Presiona 'Iniciar' para comenzar")
        
        self.root.mainloop()

if __name__ == "__main__":
    app = AudioDiagnosticTranslator()
    app.run()
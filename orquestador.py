"""
Orquestador Local — Torre de Control Asecob S.A.S.
Interfaz visual para lanzar los ciclos diarios (correo y vigilancia)
desde las estaciones de oficina, sin tocar la API en la nube.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
import tkinter as tk
from typing import Callable, Dict, List, Optional

from dotenv import load_dotenv

# Carpeta del .exe (PyInstaller) o del .py
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _resolver_python() -> List[str]:
    """
    Comando para lanzar robots.
    Si el Orquestador es .exe, usa Python del sistema (Playwright no vive bien dentro del exe).
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-u"]

    candidatos = [
        ["py", "-3", "-u"],
        ["python", "-u"],
        ["python3", "-u"],
    ]
    for cmd in candidatos:
        try:
            r = subprocess.run(
                [*cmd[:-1], "-c", "import sys; print(sys.executable)"],
                capture_output=True,
                text=True,
                timeout=8,
                cwd=str(BASE_DIR),
            )
            if r.returncode == 0 and (r.stdout or "").strip():
                return cmd
        except (OSError, subprocess.TimeoutExpired):
            continue
    return ["python", "-u"]


PYTHON_CMD = _resolver_python()

ROBOTS = {
    "correo": {
        "titulo": "1 · Cartero (correo CENDOJ)",
        "script": BASE_DIR / "robot_correo.py",
        "descripcion": "Lee Gmail, reenvía providencias y deja la bitácora Excel.",
        "args": [],
    },
    "digitador": {
        "titulo": "2 · Digitador (bitácora → Redelex)",
        "script": BASE_DIR / "robot_digitador.py",
        "descripcion": "Anota en Redelex lo que el Cartero ya gestionó.",
        "args": [],
    },
    "vigia": {
        "titulo": "1 · Vigía (RedJudicial)",
        "script": BASE_DIR / "Robot_redjudicial_2.py",
        "descripcion": "Consulta estados del día, tipifica y sube a la Torre.",
        "args": [],
    },
    "vigia_seguimiento": {
        "titulo": "Solo seguimiento (autos no disponibles)",
        "script": BASE_DIR / "Robot_redjudicial_2.py",
        "descripcion": "Relee RedJudicial y llena el Dashboard. No inyecta ni envía boletines.",
        "args": ["--solo-seguimiento"],
    },
    "redelex": {
        "titulo": "2 · Worker Redelex",
        "script": BASE_DIR / "worker_redelex.py",
        "descripcion": "Inyecta actuaciones, radica demandas del Excel y envía el boletín.",
        "args": [],
    },
}


@dataclass
class ProcesoActivo:
    nombre: str
    proceso: subprocess.Popen
    hilo_stdout: threading.Thread
    iniciado: datetime = field(default_factory=datetime.now)


class OrquestadorApp(tk.Tk):
    # Paleta ASECOB (azul corporativo, sin “look IA” genérico)
    C_BG = "#0b1f3a"
    C_PANEL = "#123258"
    C_PANEL2 = "#1a4370"
    C_ACCENT = "#e8a317"
    C_OK = "#3ecf8e"
    C_WARN = "#f5c542"
    C_TEXT = "#f1f5f9"
    C_MUTED = "#9db0c9"
    C_LOG_BG = "#071525"

    def __init__(self) -> None:
        super().__init__()
        self.title("ASECOB · Orquestador de robots")
        self.geometry("980x720")
        self.minsize(860, 620)
        self.configure(bg=self.C_BG)

        self._cola_logs: queue.Queue[str] = queue.Queue()
        self._procesos: Dict[str, ProcesoActivo] = {}
        self._estado_labels: Dict[str, ttk.Label] = {}
        self._botones_lanzar: Dict[str, ttk.Button] = {}
        self._botones_detener: Dict[str, ttk.Button] = {}
        self._ciclo_correo_activo = False
        self._ciclo_vigia_activo = False
        self._btn_ciclo_correo: Optional[tk.Button] = None
        self._btn_ciclo_vigia: Optional[tk.Button] = None
        self._btn_solo_seguimiento: Optional[tk.Button] = None
        self._lbl_prog: Optional[ttk.Label] = None
        self._lbl_estado_global: Optional[ttk.Label] = None
        self._hora_correo_var: Optional[tk.StringVar] = None
        self._hora_vigia_var: Optional[tk.StringVar] = None
        self._panel_avanzado: Optional[ttk.Frame] = None
        self._btn_toggle_avanzado: Optional[ttk.Button] = None
        self._avanzado_visible = False

        self._construir_ui()
        self.after(200, self._drenar_logs)
        self._iniciar_keepalive_render()
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    # ------------------------------------------------------------------ UI
    def _estilo(self) -> None:
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure("TFrame", background=self.C_BG)
        estilo.configure("Panel.TFrame", background=self.C_PANEL)
        estilo.configure("Panel2.TFrame", background=self.C_PANEL2)
        estilo.configure(
            "Brand.TLabel",
            font=("Segoe UI Semibold", 18),
            foreground=self.C_TEXT,
            background=self.C_PANEL,
        )
        estilo.configure(
            "Sub.TLabel",
            font=("Segoe UI", 10),
            foreground=self.C_MUTED,
            background=self.C_PANEL,
        )
        estilo.configure(
            "H2.TLabel",
            font=("Segoe UI Semibold", 12),
            foreground=self.C_ACCENT,
            background=self.C_PANEL,
        )
        estilo.configure(
            "Body.TLabel",
            font=("Segoe UI", 9),
            foreground=self.C_MUTED,
            background=self.C_PANEL,
        )
        estilo.configure(
            "Status.TLabel",
            font=("Segoe UI Semibold", 10),
            foreground=self.C_OK,
            background=self.C_PANEL,
        )
        estilo.configure(
            "CardTitle.TLabel",
            font=("Segoe UI Semibold", 11),
            foreground=self.C_TEXT,
            background=self.C_PANEL2,
        )
        estilo.configure(
            "CardBody.TLabel",
            font=("Segoe UI", 9),
            foreground=self.C_MUTED,
            background=self.C_PANEL2,
        )
        estilo.configure(
            "Estado.TLabel",
            font=("Segoe UI Semibold", 9),
            foreground="#7dd3fc",
            background=self.C_PANEL2,
        )

    def _boton_grande(
        self,
        padre: tk.Misc,
        texto: str,
        comando: Callable,
        *,
        primario: bool = True,
        ancho: int = 34,
    ) -> tk.Button:
        if primario:
            bg, fg, active = self.C_ACCENT, "#1a1205", "#f0b93a"
        else:
            bg, fg, active = "#2a5580", self.C_TEXT, "#356899"
        btn = tk.Button(
            padre,
            text=texto,
            command=comando,
            font=("Segoe UI Semibold", 11),
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=14,
            pady=12,
            cursor="hand2",
            width=ancho,
            wraplength=280,
            justify="center",
        )
        return btn

    def _construir_ui(self) -> None:
        self._estilo()
        api_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8765/api")
        nube = "onrender.com" in api_url or api_url.startswith("https://")

        # —— Cabecera marca ——
        cab = ttk.Frame(self, style="Panel.TFrame", padding=(16, 14))
        cab.pack(fill="x", padx=14, pady=(14, 8))
        ttk.Label(cab, text="GRUPO ASECOB", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(
            cab,
            text="Orquestador de robots · Correo judicial y vigilancia Redelex",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 6))
        fila_meta = ttk.Frame(cab, style="Panel.TFrame")
        fila_meta.pack(fill="x")
        color_url = self.C_OK if nube else self.C_WARN
        ttk.Label(
            fila_meta,
            text=f"{'● Nube' if nube else '● Local'}  {api_url}",
            style="Sub.TLabel",
            foreground=color_url,
        ).pack(side="left")
        tk.Button(
            fila_meta,
            text="Abrir Torre de Control",
            command=self._abrir_tablero,
            font=("Segoe UI", 9, "bold"),
            bg=self.C_PANEL2,
            fg=self.C_TEXT,
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
        ).pack(side="right")

        self._lbl_estado_global = ttk.Label(
            cab,
            text="Listo — elija un ciclo de abajo",
            style="Status.TLabel",
        )
        self._lbl_estado_global.pack(anchor="w", pady=(10, 0))

        # —— Guía rápida ——
        guia = ttk.Frame(self, style="Panel.TFrame", padding=12)
        guia.pack(fill="x", padx=14, pady=4)
        ttk.Label(guia, text="Cómo usarlo (3 pasos)", style="H2.TLabel").pack(anchor="w")
        ttk.Label(
            guia,
            text=(
                "① Pulse «1 · Correo» por la mañana → el robot lee Gmail y anota en Redelex.\n"
                "② Pulse «2 · Vigilancia» → consulta RedJudicial, registra actuaciones y radica "
                "las demandas que subieron al tablero.\n"
                "③ Abra la Torre de Control para marcar tramitados y cargar el Excel de demandas nuevas."
            ),
            style="Body.TLabel",
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        # —— Ciclos principales ——
        ciclos = ttk.Frame(self, style="Panel.TFrame", padding=12)
        ciclos.pack(fill="x", padx=14, pady=8)
        ttk.Label(ciclos, text="Ciclos del día (un clic)", style="H2.TLabel").pack(anchor="w")

        fila = ttk.Frame(ciclos, style="Panel.TFrame")
        fila.pack(fill="x", pady=(10, 4))

        col1 = ttk.Frame(fila, style="Panel.TFrame")
        col1.pack(side="left", expand=True, fill="both", padx=(0, 8))
        self._btn_ciclo_correo = self._boton_grande(
            col1,
            "1 · CORREO\nCartero → Digitador",
            self._ciclo_correo_digitador,
            primario=True,
        )
        self._btn_ciclo_correo.pack(fill="x")
        ttk.Label(
            col1,
            text="Gmail CENDOJ → abogados → bitácora → Redelex",
            style="Body.TLabel",
            wraplength=300,
        ).pack(anchor="w", pady=(6, 0))

        col2 = ttk.Frame(fila, style="Panel.TFrame")
        col2.pack(side="left", expand=True, fill="both", padx=4)
        self._btn_ciclo_vigia = self._boton_grande(
            col2,
            "2 · VIGILANCIA\nVigía → Worker Redelex",
            self._ciclo_vigia_redelex,
            primario=True,
        )
        self._btn_ciclo_vigia.pack(fill="x")
        ttk.Label(
            col2,
            text="RedJudicial → Torre → Redelex + boletín + radicación Excel",
            style="Body.TLabel",
            wraplength=300,
        ).pack(anchor="w", pady=(6, 0))

        col3 = ttk.Frame(fila, style="Panel.TFrame")
        col3.pack(side="left", expand=True, fill="both", padx=(8, 0))
        self._btn_solo_seguimiento = self._boton_grande(
            col3,
            "Solo seguimiento\nAutos no disponibles",
            self._lanzar_solo_seguimiento,
            primario=False,
        )
        self._btn_solo_seguimiento.pack(fill="x")
        ttk.Label(
            col3,
            text="Actualiza el Dashboard. No escribe en Redelex ni manda boletín.",
            style="Body.TLabel",
            wraplength=300,
        ).pack(anchor="w", pady=(6, 0))

        # —— Excel / Torre ——
        excel = ttk.Frame(self, style="Panel.TFrame", padding=12)
        excel.pack(fill="x", padx=14, pady=4)
        ttk.Label(excel, text="Demandas nuevas (Excel en la Torre)", style="H2.TLabel").pack(anchor="w")
        ttk.Label(
            excel,
            text=(
                "El Excel NO se carga en esta ventana. Se descarga y sube en el tablero web "
                "(pestaña Demandas). Cuando pulse «2 · Vigilancia», el Worker Redelex pide a la Torre "
                "la cola pendiente y radica cada fila en Redelex (nuevo.asp). "
                "La Torre es el puente: el Orquestador solo dispara el robot."
            ),
            style="Body.TLabel",
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(6, 4))
        tk.Button(
            excel,
            text="¿Cómo funciona descarga / cargue / Redelex?",
            command=self._mostrar_ayuda_excel,
            font=("Segoe UI", 9, "bold"),
            bg=self.C_PANEL2,
            fg=self.C_ACCENT,
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
        ).pack(anchor="w")

        # —— Programación ——
        prog = ttk.Frame(self, style="Panel.TFrame", padding=12)
        prog.pack(fill="x", padx=14, pady=4)
        ttk.Label(prog, text="Automático todos los días (una sola PC)", style="H2.TLabel").pack(anchor="w")
        ttk.Label(
            prog,
            text="La PC debe estar encendida y con sesión iniciada. No active esto en las dos PCs a la vez.",
            style="Body.TLabel",
            wraplength=920,
        ).pack(anchor="w", pady=(4, 8))

        self._hora_correo_var = tk.StringVar(value="07:30")
        self._hora_vigia_var = tk.StringVar(value="08:30")
        fila_h = ttk.Frame(prog, style="Panel.TFrame")
        fila_h.pack(anchor="w")
        ttk.Label(fila_h, text="Hora correo", style="Body.TLabel").pack(side="left")
        ttk.Entry(fila_h, textvariable=self._hora_correo_var, width=7).pack(side="left", padx=(6, 16))
        ttk.Label(fila_h, text="Hora vigilancia", style="Body.TLabel").pack(side="left")
        ttk.Entry(fila_h, textvariable=self._hora_vigia_var, width=7).pack(side="left", padx=(6, 16))
        ttk.Button(fila_h, text="Activar", command=self._activar_programacion).pack(side="left", padx=(0, 6))
        ttk.Button(fila_h, text="Desactivar", command=self._desactivar_programacion).pack(side="left")
        self._lbl_prog = ttk.Label(prog, text="Estado programación: …", style="Body.TLabel")
        self._lbl_prog.pack(anchor="w", pady=(8, 0))
        self.after(400, self._refrescar_estado_programacion)

        # —— Avanzado ——
        self._btn_toggle_avanzado = ttk.Button(
            self,
            text="▸  Opciones avanzadas (robots sueltos / reintentos)",
            command=self._toggle_avanzado,
        )
        self._btn_toggle_avanzado.pack(anchor="w", padx=14, pady=(6, 0))
        self._panel_avanzado = ttk.Frame(self)
        for clave, meta in ROBOTS.items():
            self._tarjeta_robot(self._panel_avanzado, clave, meta)

        # —— Consola ——
        ttk.Label(self, text="Actividad en vivo", style="Sub.TLabel", background=self.C_BG).pack(
            anchor="w", padx=18, pady=(10, 4)
        )
        self.txt_log = scrolledtext.ScrolledText(
            self,
            height=14,
            wrap="word",
            bg=self.C_LOG_BG,
            fg=self.C_TEXT,
            insertbackground=self.C_TEXT,
            font=("Consolas", 10),
            borderwidth=0,
            highlightthickness=0,
        )
        self.txt_log.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        pie = ttk.Frame(self)
        pie.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(pie, text="Detener todo", command=self._detener_todos).pack(side="left")
        ttk.Button(pie, text="Limpiar actividad", command=lambda: self.txt_log.delete("1.0", "end")).pack(
            side="left", padx=8
        )
        ttk.Button(pie, text="Carpeta de autos", command=self._abrir_autos).pack(side="right")

        self._log("Orquestador listo. Use «1 · Correo» y luego «2 · Vigilancia».")
        if getattr(sys, "frozen", False):
            self._log(f"Modo EXE · robots con: {' '.join(PYTHON_CMD)} · carpeta: {BASE_DIR}")
        if "127.0.0.1" in api_url or "localhost" in api_url:
            self._log("AVISO: API_BASE_URL es local. En oficina debe ser la URL de Render (.env).")
        else:
            self._log(f"Conectado a la Torre: {api_url}")

    def _set_estado_global(self, texto: str, ok: bool = True) -> None:
        if self._lbl_estado_global is None:
            return
        self._lbl_estado_global.configure(
            text=texto,
            foreground=self.C_OK if ok else self.C_WARN,
        )

    def _mostrar_ayuda_excel(self) -> None:
        messagebox.showinfo(
            "Excel ↔ Torre ↔ Orquestador / Worker",
            "DESCARGAR\n"
            "En la Torre (pestaña Demandas) pulse «Descargar plantilla».\n"
            "Obtiene Plantilla_Radicacion_Inteligente.xlsx con listas de ciudad y juzgado.\n\n"
            "CARGAR\n"
            "Llene el Excel y súbalo en la misma pestaña. La Torre guarda cada fila\n"
            "en la base de datos como demanda PENDIENTE. El Orquestador no lee ese archivo.\n\n"
            "REGISTRAR EN REDELEX\n"
            "Cuando corre «2 · Vigilancia», el Worker pide a la Torre\n"
            "GET /api/demandas/pendientes, abre Redelex (nuevo.asp), diligencia el formulario\n"
            "y marca cada demanda como RADICADO o ERROR en la Torre.\n\n"
            "También inyecta actuaciones de RedJudicial (cola /estados/pendientes)\n"
            "y envía el boletín único por cartera.",
        )

    def _abrir_tablero(self) -> None:
        base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
        if not base:
            api = os.getenv("API_BASE_URL", "http://127.0.0.1:8765/api")
            base = api.rsplit("/api", 1)[0].rstrip("/") or "http://127.0.0.1:8765"
        url = f"{base}/dashboard"
        webbrowser.open(url)
        self._log(f"Abriendo tablero: {url}")

    def _iniciar_keepalive_render(self) -> None:
        api_url = os.getenv("API_BASE_URL", "")
        if "onrender.com" not in api_url and not api_url.startswith("https://"):
            return
        base = api_url.rsplit("/api", 1)[0].rstrip("/")
        if not base:
            return
        intervalo = int(os.getenv("RENDER_KEEPALIVE_MINUTES", "10")) * 60

        def _loop():
            while True:
                try:
                    import requests

                    requests.get(base + "/", timeout=30)
                    self._cola_logs.put(f"[KEEPALIVE] Ping OK → {base}")
                except Exception as e:
                    self._cola_logs.put(f"[KEEPALIVE] Ping falló: {e}")
                time.sleep(max(60, intervalo))

        threading.Thread(target=_loop, daemon=True).start()
        self._log(f"Keepalive activo cada {intervalo // 60} min → {base}")

    def _toggle_avanzado(self) -> None:
        if self._panel_avanzado is None or self._btn_toggle_avanzado is None:
            return
        if self._avanzado_visible:
            self._panel_avanzado.pack_forget()
            self._btn_toggle_avanzado.configure(text="▸  Opciones avanzadas (robots sueltos / reintentos)")
            self._avanzado_visible = False
        else:
            self._panel_avanzado.pack(fill="x", padx=14, pady=4, after=self._btn_toggle_avanzado)
            self._btn_toggle_avanzado.configure(text="▾  Ocultar opciones avanzadas")
            self._avanzado_visible = True
            self._log("[AVANZADO] Robots individuales visibles — solo para reintentos puntuales.")

    def _tarjeta_robot(self, padre: ttk.Frame, clave: str, meta: dict) -> None:
        card = ttk.Frame(padre, style="Panel2.TFrame", padding=10)
        card.pack(fill="x", pady=4)
        ttk.Label(card, text=meta["titulo"], style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        estado = ttk.Label(card, text="DETENIDO", style="Estado.TLabel")
        estado.grid(row=0, column=1, sticky="e", padx=8)
        self._estado_labels[clave] = estado
        ttk.Label(card, text=meta["descripcion"], style="CardBody.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 8)
        )
        acciones = ttk.Frame(card, style="Panel2.TFrame")
        acciones.grid(row=2, column=0, columnspan=2, sticky="w")
        btn_lanzar = ttk.Button(acciones, text="Iniciar", command=lambda c=clave: self._lanzar(c))
        btn_lanzar.pack(side="left")
        btn_detener = ttk.Button(
            acciones, text="Detener", command=lambda c=clave: self._detener(c), state="disabled"
        )
        btn_detener.pack(side="left", padx=6)
        self._botones_lanzar[clave] = btn_lanzar
        self._botones_detener[clave] = btn_detener
        card.columnconfigure(0, weight=1)

    # -------------------------------------------------------------- lanzamiento
    def _lanzar(self, clave: str) -> None:
        if clave in self._procesos and self._procesos[clave].proceso.poll() is None:
            messagebox.showinfo("En ejecución", f"{ROBOTS[clave]['titulo']} ya está corriendo.")
            return

        script: Path = ROBOTS[clave]["script"]
        if not script.exists():
            messagebox.showerror(
                "Falta el robot",
                f"No se encontró {script.name} en:\n{BASE_DIR}\n\n"
                "Copie todos los archivos del kit junto al Orquestador.",
            )
            self._log(f"[ERROR] Falta {script}")
            return

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("HEADLESS_MODE", "False")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        try:
            cmd = [*PYTHON_CMD, str(script), *list(ROBOTS[clave].get("args") or [])]
            proceso = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            messagebox.showerror(
                "No se pudo iniciar",
                f"{exc}\n\nSi usa el .exe, instale Python 3.11+ y ejecute "
                "1_Instalar_Dependencias.bat en esta carpeta.",
            )
            self._log(f"[ERROR] {exc}")
            return

        hilo = threading.Thread(target=self._leer_stdout, args=(clave, proceso), daemon=True)
        hilo.start()
        self._procesos[clave] = ProcesoActivo(nombre=clave, proceso=proceso, hilo_stdout=hilo)
        if clave in self._estado_labels:
            self._estado_labels[clave].configure(text="EN EJECUCIÓN", foreground=self.C_OK)
            self._botones_lanzar[clave].configure(state="disabled")
            self._botones_detener[clave].configure(state="normal")
        self._log(f"[START] {ROBOTS[clave]['titulo']} (PID {proceso.pid})")
        self._set_estado_global(f"En curso: {ROBOTS[clave]['titulo']}", ok=True)
        threading.Thread(target=self._vigilar_salida, args=(clave, proceso), daemon=True).start()

    def _leer_stdout(self, clave: str, proceso: subprocess.Popen) -> None:
        assert proceso.stdout is not None
        for linea in proceso.stdout:
            self._cola_logs.put(f"[{clave}] {linea.rstrip()}")

    def _set_ciclo_correo_ui(self, activo: bool) -> None:
        self._ciclo_correo_activo = activo
        if self._btn_ciclo_correo is not None:
            if activo:
                self._btn_ciclo_correo.configure(state="disabled", text="Correo en curso…\nEspere")
                self._set_estado_global("Ciclo CORREO en curso (Cartero → Digitador)")
            else:
                self._btn_ciclo_correo.configure(state="normal", text="1 · CORREO\nCartero → Digitador")
                if not self._ciclo_vigia_activo:
                    self._set_estado_global("Listo — elija un ciclo de abajo")

    def _set_ciclo_vigia_ui(self, activo: bool) -> None:
        self._ciclo_vigia_activo = activo
        if self._btn_ciclo_vigia is not None:
            if activo:
                self._btn_ciclo_vigia.configure(state="disabled", text="Vigilancia en curso…\nEspere")
                self._set_estado_global("Ciclo VIGILANCIA en curso (Vigía → Worker)")
            else:
                self._btn_ciclo_vigia.configure(state="normal", text="2 · VIGILANCIA\nVigía → Worker Redelex")
                if not self._ciclo_correo_activo:
                    self._set_estado_global("Listo — elija un ciclo de abajo")

    def _ciclo_correo_digitador(self) -> None:
        self._iniciar_ciclo_secuencial(
            primero="correo",
            segundo="digitador",
            activo_flag="_ciclo_correo_activo",
            set_ui=self._set_ciclo_correo_ui,
            titulo="Correo",
        )

    def _ciclo_vigia_redelex(self) -> None:
        self._iniciar_ciclo_secuencial(
            primero="vigia",
            segundo="redelex",
            activo_flag="_ciclo_vigia_activo",
            set_ui=self._set_ciclo_vigia_ui,
            titulo="Vigilancia",
        )

    def _lanzar_solo_seguimiento(self) -> None:
        if self._ciclo_vigia_activo:
            messagebox.showinfo("Ciclo en curso", "Hay una Vigilancia completa en ejecución. Espere.")
            return
        self._log("[CAPTURA] Solo seguimiento → Dashboard (sin Redelex ni boletín).")
        self._lanzar("vigia_seguimiento")

    def _refrescar_estado_programacion(self) -> None:
        if self._lbl_prog is None:
            return
        try:
            from programacion_windows import estado_tareas

            est = estado_tareas()
            partes = []
            partes.append(
                f"Correo ACTIVO ({est.get('hora_correo') or 'diario'})"
                if est["correo"]
                else "Correo inactivo"
            )
            partes.append(
                f"Vigilancia ACTIVA ({est.get('hora_vigilancia') or 'diario'})"
                if est["vigilancia"]
                else "Vigilancia inactiva"
            )
            self._lbl_prog.configure(text="Estado programación: " + " · ".join(partes))
        except Exception as exc:
            self._lbl_prog.configure(text=f"Estado programación: no disponible ({exc})")

    def _activar_programacion(self) -> None:
        if sys.platform != "win32":
            messagebox.showinfo("Solo Windows", "La programación usa el Programador de tareas de Windows.")
            return
        hora_c = (self._hora_correo_var.get() if self._hora_correo_var else "07:30").strip()
        hora_v = (self._hora_vigia_var.get() if self._hora_vigia_var else "08:30").strip()
        try:
            from programacion_windows import activar

            msg = activar(hora_c, hora_v)
            self._log(f"[PROGRAMACIÓN] Activada — correo {hora_c}, vigilancia {hora_v}")
            messagebox.showinfo("Programación diaria", msg)
        except Exception as exc:
            messagebox.showerror("No se pudo programar", str(exc))
            self._log(f"[PROGRAMACIÓN] Error: {exc}")
        self._refrescar_estado_programacion()

    def _desactivar_programacion(self) -> None:
        if sys.platform != "win32":
            messagebox.showinfo("Solo Windows", "No hay tareas que quitar en este sistema.")
            return
        if not messagebox.askyesno("Desactivar", "¿Quitar la ejecución automática diaria en esta PC?"):
            return
        try:
            from programacion_windows import desactivar

            msg = desactivar()
            self._log("[PROGRAMACIÓN] Desactivada")
            messagebox.showinfo("Programación diaria", msg)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
        self._refrescar_estado_programacion()

    def _iniciar_ciclo_secuencial(
        self,
        *,
        primero: str,
        segundo: str,
        activo_flag: str,
        set_ui,
        titulo: str,
    ) -> None:
        if getattr(self, activo_flag):
            messagebox.showinfo("Ciclo en curso", f"Ya hay un ciclo «{titulo}» en ejecución.")
            return
        for clave in (primero, segundo):
            if clave in self._procesos and self._procesos[clave].proceso.poll() is None:
                messagebox.showinfo("En ejecución", f"{ROBOTS[clave]['titulo']} ya está corriendo.")
                return
        for clave in (primero, segundo):
            if not ROBOTS[clave]["script"].exists():
                messagebox.showerror("Falta script", str(ROBOTS[clave]["script"]))
                return

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("HEADLESS_MODE", "False")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        script = ROBOTS[primero]["script"]
        try:
            cmd = [*PYTHON_CMD, str(script), *list(ROBOTS[primero].get("args") or [])]
            proceso = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            messagebox.showerror("No se pudo iniciar", str(exc))
            return

        set_ui(True)
        hilo = threading.Thread(target=self._leer_stdout, args=(primero, proceso), daemon=True)
        hilo.start()
        self._procesos[primero] = ProcesoActivo(nombre=primero, proceso=proceso, hilo_stdout=hilo)
        if primero in self._estado_labels:
            self._estado_labels[primero].configure(text="EN EJECUCIÓN", foreground=self.C_OK)
            self._botones_lanzar[primero].configure(state="disabled")
            self._botones_detener[primero].configure(state="normal")
        self._log(
            f"[CICLO {titulo}] Paso 1/2 — {ROBOTS[primero]['titulo']}. "
            f"Al terminar OK arranca {ROBOTS[segundo]['titulo']}."
        )

        def _encadenar():
            codigo = proceso.wait()
            self._cola_logs.put(f"[END] {ROBOTS[primero]['titulo']} finalizó con código {codigo}")
            self.after(0, lambda: self._marcar_detenido(primero))
            if codigo == 0:
                self._cola_logs.put(
                    f"[CICLO {titulo}] Paso 2/2 — OK. Lanzando {ROBOTS[segundo]['titulo']}…"
                )
                self.after(300, lambda: self._lanzar_segundo_del_ciclo(segundo, set_ui, titulo))
            else:
                self._cola_logs.put(
                    f"[CICLO {titulo}] Falló el primer robot; {ROBOTS[segundo]['titulo']} no se inicia."
                )
                self.after(0, lambda: set_ui(False))

        threading.Thread(target=_encadenar, daemon=True).start()

    def _lanzar_segundo_del_ciclo(self, segundo: str, set_ui, titulo: str) -> None:
        self._lanzar(segundo)
        activo = self._procesos.get(segundo)
        if not activo:
            set_ui(False)
            return

        def _fin_ciclo():
            codigo = activo.proceso.wait()
            if codigo == 0:
                self._cola_logs.put(f"[CICLO {titulo}] Completado OK.")
                self.after(0, lambda: self._set_estado_global(f"Ciclo {titulo} terminado correctamente"))
            else:
                self._cola_logs.put(
                    f"[CICLO {titulo}] {ROBOTS[segundo]['titulo']} terminó con código {codigo}."
                )
            self.after(0, lambda: set_ui(False))

        threading.Thread(target=_fin_ciclo, daemon=True).start()

    def _vigilar_salida(self, clave: str, proceso: subprocess.Popen) -> None:
        codigo = proceso.wait()
        self._cola_logs.put(f"[END] {ROBOTS[clave]['titulo']} finalizó con código {codigo}")
        if codigo != 0:
            log_error = BASE_DIR / f"ERROR_robot_{clave}.txt"
            alt = BASE_DIR / "ERROR_robot_correo.txt"
            if clave == "correo" and alt.exists():
                self._cola_logs.put(f"[AYUDA] Abra el archivo de error: {alt}")
            elif log_error.exists():
                self._cola_logs.put(f"[AYUDA] Abra el archivo de error: {log_error}")
            else:
                self._cola_logs.put("[AYUDA] Revise .env (Gmail / Redelex / RedJudicial) y la consola.")
        self.after(0, lambda: self._marcar_detenido(clave))

    def _marcar_detenido(self, clave: str) -> None:
        self._procesos.pop(clave, None)
        if clave in self._estado_labels:
            self._estado_labels[clave].configure(text="DETENIDO", foreground="#7dd3fc")
            self._botones_lanzar[clave].configure(state="normal")
            self._botones_detener[clave].configure(state="disabled")

    def _detener(self, clave: str) -> None:
        activo = self._procesos.get(clave)
        if not activo or activo.proceso.poll() is not None:
            self._marcar_detenido(clave)
            return
        self._log(f"[STOP] Deteniendo {ROBOTS[clave]['titulo']}…")
        activo.proceso.terminate()
        try:
            activo.proceso.wait(timeout=8)
        except subprocess.TimeoutExpired:
            activo.proceso.kill()
        self._marcar_detenido(clave)
        if self._ciclo_correo_activo and clave in ("correo", "digitador"):
            self._log("[CICLO Correo] Cancelado.")
            self._set_ciclo_correo_ui(False)
        if self._ciclo_vigia_activo and clave in ("vigia", "redelex"):
            self._log("[CICLO Vigilancia] Cancelado.")
            self._set_ciclo_vigia_ui(False)

    def _detener_todos(self) -> None:
        for clave in list(self._procesos.keys()):
            self._detener(clave)
        if self._ciclo_correo_activo:
            self._set_ciclo_correo_ui(False)
        if self._ciclo_vigia_activo:
            self._set_ciclo_vigia_ui(False)

    def _abrir_autos(self) -> None:
        ruta = BASE_DIR / "AUTOS_DESCARGADOS"
        ruta.mkdir(exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(ruta))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])

    def _log(self, mensaje: str) -> None:
        if not hasattr(self, "txt_log"):
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert("end", f"{timestamp}  {mensaje}\n")
        self.txt_log.see("end")

    def _drenar_logs(self) -> None:
        while True:
            try:
                mensaje = self._cola_logs.get_nowait()
            except queue.Empty:
                break
            self._log(mensaje)
        self.after(200, self._drenar_logs)

    def _al_cerrar(self) -> None:
        vivos = [k for k, p in self._procesos.items() if p.proceso.poll() is None]
        if vivos:
            if not messagebox.askyesno("Cerrar", "Hay robots en ejecución. ¿Detenerlos y salir?"):
                return
            self._detener_todos()
        self.destroy()


def main() -> None:
    app = OrquestadorApp()
    app.mainloop()


if __name__ == "__main__":
    main()

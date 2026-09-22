import os
import sys
import time
import ast
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional

import smtplib
import requests
from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

from http_retry import get_json, patch_params

_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env")
load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# =========================================================
# CONFIGURACIÓN DEL WORKER
# =========================================================
API_BASE_URL = (os.getenv("API_BASE_URL") or "http://127.0.0.1:8765/api").rstrip("/")
API_TIMEOUT = float(os.getenv("API_TIMEOUT_SECONDS", "45"))
USUARIO_REDELEX = os.getenv("USUARIO_REDELEX", "juridico@asecobsas.com")
CLAVE_REDELEX = os.getenv("CLAVE_REDELEX")
if not CLAVE_REDELEX:
    raise ValueError(
        "Falta CLAVE_REDELEX en el archivo .env "
        f"(buscado en {_BASE_DIR / '.env'})"
    )

MODO_SANDBOX = os.getenv("MODO_SANDBOX", "False").lower() in ("true", "1")
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "False").lower() in ("true", "1")

CORREO_SISTEMA = os.getenv("CORREO_SISTEMA", "notificacionesyamidbayona@gmail.com")
CLAVE_GMAIL = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("CLAVE_GMAIL")
CORREO_SANDBOX = os.getenv("CORREO_SANDBOX", "juridico@asecobsas.com")

CORREOS_TODOS_ABOGADOS = [
    "juridico@asecobsas.com",
    "juridico2@asecobsas.com",
    "juridico3@asecobsas.com",
    "coordinacion@asecobsas.com"
]

diccionario_carteras = {
    "CONJUNTOS RESIDENCIALES": "juridico@asecobsas.com",
    "PORTAL DEL PARQUE": "juridico@asecobsas.com",
    "SOL DE GALICIA": "juridico@asecobsas.com",
    "QUINTAS DE ARAGON": "juridico@asecobsas.com",
    "BOREAL": "juridico@asecobsas.com",
    "LA AURORA": "juridico@asecobsas.com",
    "GALICIA DEL PARQUE": "juridico@asecobsas.com",
    "LAS ARAUCARIAS": "juridico@asecobsas.com",
    "CIUDAD PEREIRA": "juridico@asecobsas.com",
    "SANANDRESITO": "juridico@asecobsas.com",
    "REENCAFE": "juridico@asecobsas.com",
    "YAMID BAYONA": "juridico@asecobsas.com",
    "CREDITOS SAS": "juridico@asecobsas.com",
    "GRUPO ASECOB": "juridico2@asecobsas.com",
    "FONDO DE GARANTIAS": "juridico2@asecobsas.com",
    "COMFAMILIAR": "juridico2@asecobsas.com",
    "FINANFUTURO": "juridico2@asecobsas.com",
    "FUNDACION AMANECER": "juridico3@asecobsas.com",
    "SUZUKI": "juridico3@asecobsas.com",
    "GRUPO TROPI": "juridico3@asecobsas.com",
    "ACTUAR QUINDIO": "juridico3@asecobsas.com",
    "COMERCIALIZADORA SANTANDER": "juridico3@asecobsas.com",
    "GEES GLOBAL": "juridico3@asecobsas.com"
}

PALABRAS_PROHIBIDAS = {
    "BANCO", "FUNDACION", "CONDOMINIO", "CONJUNTO", "EDIFICIO",
    "SAS", "S.A.", "S.A.S.", "LTDA", "CONTRA", "CIVIL",
    "MUNICIPAL", "PROMISCUO", "ORIGEN"
}

def ocultar_datepicker_y_desenfocar(page: Page):
    try:
        page.evaluate("""
            if (document.getElementById('ui-datepicker-div')) {
                document.getElementById('ui-datepicker-div').style.display = 'none';
            }
            if (document.activeElement) {
                document.activeElement.blur();
            }
        """)
    except Exception:
        pass

def login_redelex(page: Page):
    print("\n-> Iniciando sesión en Redelex con protocolo blindado...")
    page.goto("https://cloudapp.redelex.com/sso/redelex/login?auth=1")

    page.locator("#userName").wait_for(state="visible", timeout=15000)
    page.locator("#userName").fill(USUARIO_REDELEX)
    time.sleep(1)

    page.evaluate("document.getElementById('btn_continue').click();")
    time.sleep(2)

    page.locator("#userLoginPwd").fill(CLAVE_REDELEX, force=True)
    time.sleep(1)
    page.evaluate("document.getElementById('btnIngresarOAuth').dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));")
    time.sleep(5)

    if "expirada" in page.url.lower() or page.locator('text="Sesión Expirada"').is_visible(timeout=3000):
        print("   [ALERTA] Choque de sesión detectado. Reingresando...")
        try:
            page.locator('a:has-text("Iniciar sesión")').click()
            time.sleep(3)
            page.locator("#userName").fill(USUARIO_REDELEX)
            time.sleep(1)
            page.evaluate("document.getElementById('btn_continue').click();")
            time.sleep(2)
            page.locator("#userLoginPwd").fill(CLAVE_REDELEX, force=True)
            time.sleep(1)
            page.evaluate("document.getElementById('btnIngresarOAuth').dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));")
            time.sleep(5)
        except Exception as e:
            print(f"   [WARN] Error en re-login: {e}")

    page.goto("https://cloudapp.redelex.com/procesos/home_cuenta.asp", timeout=15000)
    time.sleep(2)
    print("   [OK] Sesión confirmada en Redelex.")

def verificar_sesion_activa(page: Page):
    if "login" in page.url.lower() or "expirada" in page.url.lower():
        print("   [SESIÓN PERDIDA] Re-autenticando en Redelex...")
        login_redelex(page)

# =========================================================
# FRENTE 2: INYECCIÓN DE ESTADOS JUDICIALES
# =========================================================
def procesar_inyeccion_estados(page: Page):
    print("\n==========================================")
    print(" EJECUTANDO FRENTE 2: ESTADOS REDJUDICIAL ")
    print(f" API: {API_BASE_URL}/estados/pendientes")
    print("==========================================")

    try:
        pendientes = get_json(f"{API_BASE_URL}/estados/pendientes", timeout=API_TIMEOUT)
    except Exception as e:
        print(f"[ERROR API] No se pudo consultar estados pendientes: {e}")
        return

    if not pendientes:
        print("Sin estados judiciales pendientes por inyectar.")
        return

    print(f"Total estados pendientes recibidos: {len(pendientes)}")
    lista_notificaciones_exitosas = []
    fecha_proceso_str = datetime.now().strftime("%Y-%m-%d")

    for item in pendientes:
        item_id = item["id"]
        radicado = str(item["radicado"]).strip()
        demandante = str(item.get("demandante", "")).strip().upper()
        demandado = str(item.get("demandado", "")).strip().upper()
        etapa_ia = item.get("etapa_ia")
        actuacion_ia = item.get("actuacion_ia")
        resumen_ia = item.get("resumen_ia") or ""
        fecha_notif = item.get("fecha_notificacion")
        ruta_pdf_local = item.get("ruta_pdf_local")

        if isinstance(actuacion_ia, str) and actuacion_ia.startswith("[") and actuacion_ia.endswith("]"):
            try:
                lista_act = ast.literal_eval(actuacion_ia)
                if len(lista_act) >= 2:
                    etapa_ia = str(lista_act[0]).strip()
                    actuacion_ia = str(lista_act[1]).strip()
            except Exception:
                pass

        print(f"\n--- Procesando Radicado: {radicado} (ID BD: {item_id}) ---")
        verificar_sesion_activa(page)

        try:
            page.goto("https://cloudapp.redelex.com/procesos/search.asp", timeout=15000)
            page.wait_for_selector("input#txtNumeroRadicacion", timeout=8000)
            page.fill("input#txtNumeroRadicacion", radicado)
            page.click("input#rbTodos")
            page.click('button:has-text("Buscar")')
            time.sleep(3)

            filas_resultados = page.locator("tr.clickable-row")
            cantidad = filas_resultados.count()

            if cantidad == 0:
                print("   [AVISO] Radicado no encontrado en Redelex.")
                reportar_resultado_estado(item_id, "FALLIDO", "Radicado no encontrado en Redelex")
                continue

            dem_limpio = demandante.split("-")[0].strip()
            dda_limpio = demandado.split("-")[0].strip()
            palabras_dem = [p for p in dem_limpio.split() if len(p) > 3]
            palabras_dda = [p for p in dda_limpio.split() if len(p) > 3]
            palabras_clave = [p for p in (palabras_dem + palabras_dda) if p not in PALABRAS_PROHIBIDAS] or (palabras_dem + palabras_dda)

            radicado_limpio = radicado.replace("-", "")
            mejor_fila = -1
            max_coincidencias = 0

            for i in range(cantidad):
                texto_fila = filas_resultados.nth(i).inner_text().upper().replace("-", "")
                if radicado_limpio not in texto_fila:
                    continue
                coincidencias = sum(1 for pal in palabras_clave if pal in texto_fila)
                if coincidencias > max_coincidencias:
                    max_coincidencias = coincidencias
                    mejor_fila = i

            if mejor_fila == -1:
                print("   [AVISO] Falso positivo: Las partes procesales no coinciden.")
                reportar_resultado_estado(item_id, "FALLIDO", "Falso positivo en partes procesales")
                continue

            filas_resultados.nth(mejor_fila).click()
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)

            tab_actuaciones = page.locator('a:has-text("Actuaciones")').first
            try:
                tab_actuaciones.wait_for(state="visible", timeout=8000)
                tab_actuaciones.click()
                time.sleep(2)
            except Exception:
                pass

            btn_nueva = page.locator("input#btn_nueva_actuacion")
            btn_nueva.wait_for(state="visible", timeout=8000)
            btn_nueva.click()
            time.sleep(1)

            if etapa_ia:
                try:
                    page.locator("#etapas").select_option(label=etapa_ia, timeout=3000)
                    page.wait_for_timeout(1200)
                except Exception:
                    print(f"   [WARN] No se pudo seleccionar la etapa: {etapa_ia}")

            try:
                page.locator("#actuaciones").select_option(label=actuacion_ia, timeout=3000)
            except Exception:
                try:
                    page.locator("#actuaciones").select_option(label="AUTO - CAUSAL", timeout=3000)
                except Exception:
                    page.locator("#actuaciones").select_option(index=1, timeout=3000)

            if fecha_notif:
                page.evaluate(f"document.getElementById('fecha_actuacion').value = '{fecha_notif}';")
            ocultar_datepicker_y_desenfocar(page)
            page.locator("textarea#observacion").fill(resumen_ia)

            if MODO_SANDBOX:
                print("   [SANDBOX] Formulario validado con éxito. Guardado omitido.")
            else:
                page.locator("input#submitNewAct").first.click(force=True)
                page.wait_for_load_state("networkidle")
                time.sleep(3)
                print(f"   [PRODUCCIÓN] Actuación guardada formalmente en Redelex para {radicado}.")
                reportar_resultado_estado(item_id, "EXITOSO", "Inyectado formalmente en Redelex")
                
                lista_notificaciones_exitosas.append({
                    "radicado": radicado,
                    "demandante": demandante,
                    "demandado": demandado,
                    "etapa_ia": etapa_ia,
                    "actuacion_ia": actuacion_ia,
                    "resumen_ia": resumen_ia,
                    "ruta_pdf_local": ruta_pdf_local
                })

        except Exception as e:
            print(f"   [ERROR] Excepción procesando radicado {radicado}: {e}")
            reportar_resultado_estado(item_id, "FALLIDO", str(e)[:150])

    if lista_notificaciones_exitosas:
        enviar_boletines_worker(lista_notificaciones_exitosas, fecha_proceso_str)

def reportar_resultado_estado(estado_id: int, estado_inyeccion: str, motivo: str):
    try:
        url = f"{API_BASE_URL}/estados/{estado_id}/actualizar"
        patch_params(
            url,
            {"estado_inyeccion": estado_inyeccion, "motivo_falla": motivo},
            timeout=API_TIMEOUT,
        )
    except Exception as e:
        print(f"   [ERROR API] No se pudo actualizar estado en BD: {e}")

# =========================================================
# MOTOR DE NOTIFICACIONES POR CORREO DEL WORKER
# =========================================================
def enviar_boletines_worker(lista_exitosos: List[Dict], fecha_str: str):
    print("\n" + "=" * 60)
    print(" DESPACHO DE BOLETINES A ABOGADOS ASIGNADOS")
    print("=" * 60)

    def encontrar_destinatario(demandante):
        if MODO_SANDBOX:
            return CORREO_SANDBOX
        dem_upper = str(demandante).upper()
        for clave, correo in diccionario_carteras.items():
            if clave in dem_upper:
                return correo
        return "TODOS"

    grupos = {}
    for item in lista_exitosos:
        dest = encontrar_destinatario(item["demandante"])
        grupos.setdefault(dest, []).append(item)

    prefijo = "[PRUEBA SANDBOX] " if MODO_SANDBOX else ""

    for destino, autos in grupos.items():
        try:
            msg = EmailMessage()
            msg["From"] = CORREO_SISTEMA

            if destino == "TODOS":
                msg["Subject"] = f"{prefijo}[CARTERA NO IDENTIFICADA] Boletín Estados Judiciales - {fecha_str}"
                msg["To"] = ", ".join(CORREOS_TODOS_ABOGADOS)
            else:
                msg["Subject"] = f"{prefijo}Boletín Diario de Actuaciones Judiciales - {fecha_str}"
                msg["To"] = destino

            cuerpo = f"Buen día,\n\nA continuación se relacionan las actuaciones procesales inyectadas en Redelex ({len(autos)}):\n\n"
            for a in autos:
                cuerpo += f"• Radicado: {a['radicado']}\n"
                cuerpo += f"  Partes: {a['demandante']} vs {a['demandado']}\n"
                cuerpo += f"  Etapa: {a['etapa_ia']} | {a['actuacion_ia']}\n"
                cuerpo += f"  Resumen: {a['resumen_ia']}\n\n"

            cuerpo += "Torre de Control & Automatización Procesal - Grupo Asecob S.A.S.\n"
            msg.set_content(cuerpo)

            for a in autos:
                ruta_pdf = a.get("ruta_pdf_local")
                if ruta_pdf and os.path.exists(ruta_pdf):
                    with open(ruta_pdf, "rb") as f:
                        msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename=os.path.basename(ruta_pdf))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(CORREO_SISTEMA, CLAVE_GMAIL)
                smtp.send_message(msg)
            print(f" [OK] Boletín ({len(autos)} autos) enviado a: {msg['To']}")

        except Exception as e:
            print(f" [ERROR CORREO] Fallo enviando boletín a {destino}: {e}")

# =========================================================
# FRENTE 3: RADICACIÓN MASIVA DE DEMANDAS NUEVAS
# =========================================================
# Orden DOM real (nuevo.asp, antes de #btn_submit):
#  1 Cliente  2 Tema(opc)  3 Radicación|#sin_numero  4 Referencia
#  5 Clase Proceso  6 Tipo Juzgado/Despacho  7 Numero  8 Ciudad
#  9 Regional 10 Estado 11 Tipo Intervención 12 Guardar

CLASE_PROCESO_VALORES = {
    "EJECUTIVO": "32387",
    "EJECUTIVO HIPOTECARIO": "32357",
    "EJECUTIVO PRENDARIO": "32356",
    "VERBAL": "32487",
    "ABREVIADO": "32361",
    "LABORAL ORDINARIO": "32360",
    "ACCION DE TUTELA": "32367",
    "CONCILIACION PREJUDICIAL": "32377",
    "-- SIN ESPECIFICAR --": "32491",
    "SIN ESPECIFICAR": "32491",
}


def _seleccionar_por_label_o_valor(page: Page, selector: str, texto: str, timeout: int = 4000) -> bool:
    """Intenta select_option por label exacto, value, o label parcial."""
    if not texto:
        return False
    loc = page.locator(selector)
    if loc.count() == 0:
        return False
    try:
        loc.first.select_option(label=texto, timeout=timeout)
        return True
    except Exception:
        pass
    try:
        loc.first.select_option(value=str(texto), timeout=timeout)
        return True
    except Exception:
        pass
    # Búsqueda parcial en opciones
    try:
        opciones = loc.first.locator("option").all()
        key = texto.strip().upper()
        for op in opciones:
            lab = (op.inner_text() or "").strip()
            val = op.get_attribute("value") or ""
            if key == lab.upper() or key == val or key in lab.upper():
                loc.first.select_option(value=val, timeout=timeout)
                return True
    except Exception as e:
        print(f"   [WARN] No se pudo seleccionar {selector}={texto!r}: {e}")
    return False


def _diligenciar_radicacion_form(page: Page, d: dict) -> None:
    """Rellena #nuevoExpediente según reglas de negocio Excel → Redelex."""
    from catalogos_redelex import resolver_tipo_juzgado, resolver_valor_ciudad

    radicacion = (d.get("radicacion") or "").strip() if d.get("radicacion") else ""
    referencia = (d.get("referencia") or "").strip() if d.get("referencia") else ""
    if not referencia:
        nombre = f"{d.get('nombres_demandado', '')} {d.get('apellidos_demandado', '')}".strip()
        referencia = nombre or f"Demanda {d.get('identificacion_demandado', '')}"

    clase = (d.get("clase_proceso") or "EJECUTIVO").strip()
    tipo_juz = resolver_tipo_juzgado(d.get("tipo_juzgado")) or (d.get("tipo_juzgado") or "").strip()
    numero = (d.get("numero_juzgado") or "").strip() or "0"
    if len(numero) > 4:
        numero = numero[:4]
    ciudad_raw = d.get("ciudad_juzgado")
    ciudad_val = resolver_valor_ciudad(ciudad_raw) if ciudad_raw else None

    # 3. Radicación / Sin Número
    if page.locator("#radicacion").count():
        if radicacion:
            page.fill("#radicacion", radicacion)
            # Desmarcar sin_numero si estaba marcado
            if page.locator("#sin_numero").is_checked():
                page.uncheck("#sin_numero", force=True)
            print(f"   [OK] Radicación: {radicacion}")
        else:
            page.fill("#radicacion", "")
            if page.locator("#sin_numero").count():
                page.check("#sin_numero", force=True)
                print("   [OK] Sin número de radicación (checkbox #sin_numero)")
            else:
                print("   [WARN] Checkbox #sin_numero no encontrado; radicación vacía")

    # 4. Referencia
    for sel in ['textarea[name="referencia"]', "#referencia", 'textarea[placeholder*="eferencia"]']:
        if page.locator(sel).count():
            page.fill(sel, referencia[:500])
            print(f"   [OK] Referencia: {referencia[:60]}")
            break

    # 5. Clase Proceso
    valor_clase = CLASE_PROCESO_VALORES.get(clase.upper(), None)
    if valor_clase:
        ok = _seleccionar_por_label_o_valor(page, 'select[name="clase_proceso"]', valor_clase)
        if not ok:
            _seleccionar_por_label_o_valor(page, 'select[name="clase_proceso"]', clase)
    else:
        _seleccionar_por_label_o_valor(page, 'select[name="clase_proceso"]', clase)
    print(f"   [OK] Clase proceso: {clase}")

    # 6. Tipo Juzgado / Despacho
    if tipo_juz:
        ok = False
        for sel in [
            'select[name="tipo_juzgado"]',
            'select[name="despacho"]',
            'select[name="tipo_despacho"]',
            'select#tipo_juzgado',
        ]:
            if page.locator(sel).count():
                ok = _seleccionar_por_label_o_valor(page, sel, tipo_juz)
                if ok:
                    print(f"   [OK] Tipo juzgado: {tipo_juz}")
                    break
        if not ok:
            print(f"   [WARN] No se seleccionó tipo juzgado: {tipo_juz}")

    # 7. Numero juzgado (default 0)
    if page.locator("#numero_juzgado").count():
        page.fill("#numero_juzgado", numero)
    elif page.locator('input[name="numero_juzgado"]').count():
        page.fill('input[name="numero_juzgado"]', numero)
    print(f"   [OK] Numero juzgado: {numero}")

    # 8. Ciudad juzgado
    if ciudad_val or ciudad_raw:
        target = ciudad_val or str(ciudad_raw)
        ok = _seleccionar_por_label_o_valor(page, 'select[name="ciudad_juzgado"]', target)
        if not ok and ciudad_raw:
            ok = _seleccionar_por_label_o_valor(page, 'select[name="ciudad_juzgado"]', str(ciudad_raw))
        print(f"   [{'OK' if ok else 'WARN'}] Ciudad juzgado: {ciudad_raw} → value={ciudad_val}")


def procesar_radicacion_demandas(page: Page):
    print("\n==========================================")
    print(" EJECUTANDO FRENTE 3: RADICACIÓN DEMANDAS ")
    print("==========================================")

    try:
        demandas_pendientes = get_json(f"{API_BASE_URL}/demandas/pendientes", timeout=API_TIMEOUT)
    except Exception as e:
        print(f"[ERROR API] No se pudo consultar demandas pendientes: {e}")
        return

    if not demandas_pendientes:
        print("Sin demandas nuevas pendientes por radicar.")
        return

    print(f"Total demandas pendientes de radicación: {len(demandas_pendientes)}")

    for d in demandas_pendientes:
        demanda_id = d["id"]
        ident_demandado = d.get("identificacion_demandado") or ""
        nombre_demandado = f"{d.get('nombres_demandado', '')} {d.get('apellidos_demandado', '')}".strip()
        cuantia = d.get("monto_pretension", 0.0) or 0.0

        print(f"\n--- Radicando Demanda ID: {demanda_id} | Demandado: {nombre_demandado} ({ident_demandado}) ---")
        verificar_sesion_activa(page)

        try:
            page.goto("https://cloudapp.redelex.com/procesos/nuevo.asp", timeout=20000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)

            # Campos legacy si aún existen en alguna variante del form
            if page.locator("#txtIdentificacionDemandado").is_visible():
                page.fill("#txtIdentificacionDemandado", ident_demandado)
            if page.locator("#txtNombreDemandado").is_visible():
                page.fill("#txtNombreDemandado", nombre_demandado)
            if page.locator("#txtCuantia").is_visible():
                page.fill("#txtCuantia", str(int(float(cuantia))))

            # Formulario real nuevo.asp (orden antes de Guardar)
            if page.locator("#radicacion").count() or page.locator('select[name="ciudad_juzgado"]').count():
                _diligenciar_radicacion_form(page, d)
            else:
                print("   [WARN] Selectores nuevo.asp no visibles; solo campos legacy rellenados.")

            ocultar_datepicker_y_desenfocar(page)

            if MODO_SANDBOX:
                print("   [SANDBOX] Formulario diligenciado. Click Guardar omitido.")
                reportar_resultado_demanda(demanda_id, "PENDIENTE", "Sandbox: sin click Guardar")
            else:
                # Preferir #btn_submit (DOM real); fallback legacy
                if page.locator("#btn_submit").count():
                    page.click("#btn_submit", force=True)
                elif page.locator("button#btnGuardarDemanda").count():
                    page.click("button#btnGuardarDemanda", force=True)
                elif page.locator('input[type="submit"][value*="Guardar"]').count():
                    page.click('input[type="submit"][value*="Guardar"]', force=True)
                else:
                    page.get_by_role("button", name="Guardar").click(force=True)
                time.sleep(3)
                print(f"   [PRODUCCIÓN] Demanda {demanda_id} enviada en Redelex.")
                reportar_resultado_demanda(demanda_id, "RADICADO", "Radicación enviada (#btn_submit)")

        except Exception as e:
            print(f"   [ERROR] Excepción radicando demanda ID {demanda_id}: {e}")
            reportar_resultado_demanda(demanda_id, "ERROR", str(e)[:150])


def reportar_resultado_demanda(demanda_id: int, estado_robot: str, motivo: str = ""):
    try:
        url = f"{API_BASE_URL}/demandas/{demanda_id}/actualizar"
        patch_params(url, {"estado_robot": estado_robot, "motivo_error": motivo}, timeout=API_TIMEOUT)
    except Exception as e:
        print(f"   [ERROR API] No se pudo actualizar demanda en BD: {e}")


# =========================================================
# ORQUESTADOR PRINCIPAL DEL WORKER
# =========================================================
def _despertar_api():
    base = API_BASE_URL.rsplit("/api", 1)[0].rstrip("/") or API_BASE_URL
    if not base.startswith("http"):
        return
    try:
        requests.get(base + "/", timeout=30)
        print(f"[API] Ping OK -> {base}")
    except Exception as e:
        print(f"[API] Ping previo fallo (se reintentara): {e}")


def ejecutar_worker():
    print("=========================================")
    print(" WORKER REDELEX — Torre de Control")
    print(f" API: {API_BASE_URL}")
    print(f" Sandbox: {MODO_SANDBOX} | Headless: {HEADLESS_MODE}")
    print("=========================================")
    _despertar_api()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS_MODE,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        login_redelex(page)
        procesar_inyeccion_estados(page)
        procesar_radicacion_demandas(page)

        print("\n[FIN] Ciclo unificado del Worker completado exitosamente.")
        browser.close()


if __name__ == "__main__":
    try:
        ejecutar_worker()
    except Exception as e:
        print(f"[ABORTADO] {type(e).__name__}: {e}")
        sys.exit(1)
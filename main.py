import streamlit as st
import pandas as pd
import os
import pydeck as pdk
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from streamlit_gsheets import GSheetsConnection
import sqlite3

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Europa 2026 Pro", layout="wide")
FOLDER_ADJUNTOS = "mis_adjuntos"
if not os.path.exists(FOLDER_ADJUNTOS):
    os.makedirs(FOLDER_ADJUNTOS)

# --- 1. CONFIGURACIÓN DE BASE DE DATOS ---
DB_NAME = "viaje_europa_2026.db"

if os.path.exists(DB_NAME): os.remove(DB_NAME) # Borra esto tras la primera ejecución
    
init_db()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Tabla Itinerario con los nombres EXACTOS que espera tu código
    c.execute('''CREATE TABLE IF NOT EXISTS itinerario
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  "Fecha" TEXT, "País" TEXT, "Ciudad" TEXT, 
                  "Traslado $" REAL, "P. Traslado" INTEGER, 
                  "Aloj. $" REAL, "P. Aloj" INTEGER, 
                  "Comida $" REAL, "P. Comida" INTEGER, 
                  "Otros $" REAL, "Notas" TEXT)''')
    
    # Tabla Globales
    c.execute('''CREATE TABLE IF NOT EXISTS globales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  "Pagado" INTEGER, "Descripción" TEXT, "Monto $" REAL)''')
    
    # Tabla Detalles Otros
    c.execute('''CREATE TABLE IF NOT EXISTS detalles_otros
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  "Fecha" TEXT, "Categoría/Descripción" TEXT, "Monto $" REAL, "Pagado" INTEGER)''')
    conn.commit()
    conn.close()

# Inicializamos la DB al cargar la app
init_db()

def cargar_datos_sql(tabla):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(f"SELECT * FROM {tabla}", conn)
    conn.close()
    if 'id' in df.columns: df = df.drop(columns=['id'])
    return df

def guardar_datos_sql(df, tabla):
    conn = sqlite3.connect(DB_NAME)
    # Reemplazamos la tabla completa con el nuevo DataFrame
    df.to_sql(tabla, conn, if_exists='replace', index=False)
    conn.commit()
    conn.close()
    st.toast(f"✅ Guardado en base de datos interna ({tabla})")
@st.cache_data
def obtener_coordenadas(ciudad, pais):
    try:
        geolocator = Nominatim(user_agent="itinerario_v26")
        location = geolocator.geocode(f"{ciudad}, {pais}")
        if location: return [location.latitude, location.longitude]
    except: return None

# --- 3. INICIALIZACIÓN ---
df_it = cargar_datos_sql("itinerario")
df_gl = cargar_datos_sql("globales")
df_detalles = cargar_datos_sql("detalles_otros")

# Si las tablas están vacías (primera vez), creamos esquemas vacíos
if df_it.empty:
    df_it = pd.DataFrame(columns=["fecha", "pais", "ciudad", "traslado_monto", "traslado_pago", 
                                   "aloj_monto", "aloj_pago", "comida_monto", "comida_pago", "otros_monto", "notas"])
if df_gl.empty:
    df_gl = pd.DataFrame(columns=["pagado", "descripcion", "monto"])

# Limpieza de tipos para evitar errores de cálculo
for df in [df_it, df_gl, df_detalles]:
    if "Monto $" in df.columns: df["Monto $"] = pd.to_numeric(df["Monto $"], errors='coerce').fillna(0.0)
    if "Pagado" in df.columns: df["Pagado"] = df["Pagado"].astype(bool)
# (Repetir para las columnas específicas de df_it si es necesario)
for c in ["Traslado $", "Aloj. $", "Comida $", "Otros $"]:
    df_it[c] = pd.to_numeric(df_it[c], errors='coerce').fillna(0.0)
for c in ["P. Traslado", "P. Aloj", "P. Comida"]:
    df_it[c] = df_it[c].astype(bool)

# --- 4. CÁLCULOS Y SIDEBAR ---
st.sidebar.markdown("---")
st.sidebar.subheader("📦 Gestión de Datos")

# Botón para descargar todo como un archivo SQLite (Backup real)
with open(DB_NAME, "rb") as f:
    st.sidebar.download_button(
        label="📥 Descargar Backup (.db)",
        data=f,
        file_name="backup_viaje.db",
        mime="application/x-sqlite3"
    )

# Botón para subir un backup previo
uploaded_db = st.sidebar.file_uploader("📤 Restaurar Backup", type="db")
if uploaded_db:
    with open(DB_NAME, "wb") as f:
        f.write(uploaded_db.getbuffer())
    st.sidebar.success("Base de datos restaurada. Recargando...")
    st.rerun()

st.sidebar.header("⚙️ Configuración")
f_ini = st.sidebar.date_input("Inicio", datetime.now())
f_fin = st.sidebar.date_input("Fin", datetime.now() + timedelta(days=7))

if st.sidebar.button("Reiniciar Itinerario"):
    with st.spinner("Comunicando con Google..."):
        dias = (f_fin - f_ini).days + 1
        nuevas_filas = []
        for i in range(dias):
            fecha_str = (f_ini + timedelta(days=i)).strftime("%d/%m (%a)")
            nuevas_filas.append({
                "Fecha": fecha_str, "País": "", "Ciudad": "", 
                "Traslado $": 0.0, "P. Traslado": False, 
                "Aloj. $": 0.0, "P. Aloj": False, 
                "Comida $": 0.0, "P. Comida": False, 
                "Otros $": 0.0, "Notas": ""
            })
        
        df_it_nuevo = pd.DataFrame(nuevas_filas)
        guardar_en_google(df_it_nuevo, "Itinerario")
        st.success("Itinerario creado con éxito.")
        # No hacemos rerun instantáneo para dejar que Google procese
        st.info("Por favor, refresca la página manualmente en 5 segundos.")

# Lógica de Totales
total_plan = df_it[["Traslado $", "Aloj. $", "Comida $"]].sum().sum() + df_detalles["Monto $"].sum() + df_gl["Monto $"].sum()
pag_it = df_it.loc[df_it["P. Traslado"], "Traslado $"].sum() + df_it.loc[df_it["P. Aloj"], "Aloj. $"].sum() + df_it.loc[df_it["P. Comida"], "Comida $"].sum()
total_pag = pag_it + df_it["Otros $"].sum() + df_gl.loc[df_gl["Pagado"], "Monto $"].sum()

st.sidebar.metric("Presupuesto Total", f"$ {total_plan:,.2f}")
st.sidebar.metric("Ya Pagado", f"$ {total_pag:,.2f}")
st.sidebar.metric("Pendiente", f"$ {total_plan - total_pag:,.2f}")

# --- 5. TABS ---
t1, t2, t3, t4 = st.tabs(["📅 Itinerario", "🎒 Globales", "📂 Adjuntos", "📍 Mapa"])

with t1:
    df_it_edit = st.data_editor(df_it, num_rows="dynamic", width="stretch", hide_index=True)
    if not df_it_edit.equals(df_it):
        guardar_en_google(df_it_edit, "Itinerario"); st.rerun()

# --- 1. LÓGICA DE PROTECCIÓN PARA DETALLES ---
    st.markdown("---")
    st.subheader("🕵️ Desglose de 'Otros'")
    
    # Aseguramos que dia_sel sea válido
    lista_fechas = df_it_edit["Fecha"].tolist()
    dia_sel = st.selectbox("Día para detallar:", lista_fechas)
    
    # Filtramos los detalles del día
    det_dia = df_detalles[df_detalles["Fecha"] == dia_sel].drop(columns=["Fecha"]).reset_index(drop=True)
    
    # FUERZA BRUTA: Si la tabla está vacía, aseguramos las columnas para que no de ValueError
    for col in ["Categoría/Descripción", "Monto $", "Pagado"]:
        if col not in det_dia.columns:
            det_dia[col] = False if col == "Pagado" else (0.0 if "$" in col else "")

    # Editor de detalles
    det_edit = st.data_editor(
        det_dia, 
        num_rows="dynamic", 
        width="stretch", 
        hide_index=True,
        key=f"ed_{dia_sel}"
    )
    
    if not det_edit.equals(det_dia):
        # 1. Reconstruir el DataFrame completo de detalles
        df_detalles_nuevo = pd.concat([df_detalles[df_detalles["Fecha"] != dia_sel], det_edit.assign(Fecha=dia_sel)], ignore_index=True)
        
        # 2. Guardar en Google
        guardar_en_google(df_detalles_nuevo, "Detalles_Otros")
        
        # 3. ACTUALIZACIÓN SEGURA DEL TOTAL (Aquí es donde daba el error)
        # Verificamos que existan datos antes de sumar
        if not det_edit.empty and "Pagado" in det_edit.columns:
            # Forzamos que Pagado sea booleano para evitar el ValueError
            det_edit["Pagado"] = det_edit["Pagado"].astype(bool)
            total_pagado_dia = det_edit.loc[det_edit["Pagado"] == True, "Monto $"].sum()
        else:
            total_pagado_dia = 0.0
            
        df_it_edit.loc[df_it_edit["Fecha"] == dia_sel, "Otros $"] = total_pagado_dia
        guardar_en_google(df_it_edit, "Itinerario")
        st.rerun()

with t2:
    st.subheader("Gastos Globales")
    df_gl_edit = st.data_editor(df_gl, num_rows="dynamic", width="stretch", hide_index=True)
    if not df_gl_edit.equals(df_gl):
        guardar_en_google(df_gl_edit, "Globales"); st.rerun()

with t3:
    st.info("La gestión de archivos adjuntos se guarda localmente en el servidor.")
    if not df_it_edit.empty:
        # Selector del día para ver/subir archivos
        dia_adjunto = st.selectbox("Selecciona el día para gestionar archivos:", df_it_edit["Fecha"].tolist(), key="sel_adj")
        
        # Crear carpeta limpia para el nombre del archivo
        nombre_carpeta = dia_adjunto.replace("/", "-").replace(" ", "_")
        ruta_dia = os.path.join(FOLDER_ADJUNTOS, nombre_carpeta)
        
        if not os.path.exists(ruta_dia):
            os.makedirs(ruta_dia)
            
        # Subida de archivos
        archivo_nuevo = st.file_uploader(f"Subir archivo para {dia_adjunto}:", key=f"up_{nombre_carpeta}")
        
        if archivo_nuevo is not None:
            with open(os.path.join(ruta_dia, archivo_nuevo.name), "wb") as f:
                f.write(archivo_nuevo.getbuffer())
            st.success(f"¡{archivo_nuevo.name} guardado correctamente!")
            st.rerun()

        st.markdown("---")
        st.write(f"Archivos guardados para el día **{dia_adjunto}**:")
        
        archivos_en_carpeta = os.listdir(ruta_dia)
        if archivos_en_carpeta:
            for arc in archivos_en_carpeta:
                col_n, col_d = st.columns([0.8, 0.2])
                col_n.write(f"📄 {arc}")
                with open(os.path.join(ruta_dia, arc), "rb") as f:
                    col_d.download_button("Bajar", f, file_name=arc, key=f"dl_{arc}")
        else:
            st.warning("No hay archivos adjuntos para este día todavía.")
    else:
        st.info("Genera un itinerario primero para poder adjuntar archivos.")

with t4:
    st.subheader("🗺️ Ruta")
    df_m = df_it_edit[(df_it_edit["Ciudad"]!="") & (df_it_edit["País"]!="")].copy()
    puntos = []
    for _, r in df_m.iterrows():
        c = obtener_coordenadas(r["Ciudad"], r["País"])
        if c: puntos.append({"lat": c[0], "lon": c[1], "name": r["Ciudad"]})
    
    if len(puntos) >= 2:
        df_p = pd.DataFrame(puntos)
        rutas = [{"start": [puntos[i]["lon"], puntos[i]["lat"]], "end": [puntos[i+1]["lon"], puntos[i+1]["lat"]]} for i in range(len(puntos)-1)]
        st.pydeck_chart(pdk.Deck(map_style='light', initial_view_state=pdk.ViewState(latitude=df_p["lat"].mean(), longitude=df_p["lon"].mean(), zoom=3, pitch=45),
            layers=[pdk.Layer("ArcLayer", rutas, get_source_position="start", get_target_position="end", get_width=3),
                    pdk.Layer("ScatterplotLayer", df_p, get_position="[lon, lat]", get_radius=20000, get_color="[200, 30, 0]")]))

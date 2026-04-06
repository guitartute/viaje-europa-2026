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

DB_NAME = "viaje_europa_2026_4.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tabla Itinerario: Nombres entre comillas dobles para caracteres especiales
    c.execute('''
        CREATE TABLE IF NOT EXISTS itinerario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "Fecha" TEXT,
            "Pais" TEXT,
            "Ciudad" TEXT,
            "Traslado_Monto" REAL,
            "Traslado_Pago" INTEGER,
            "Aloj_Monto" REAL,
            "Aloj_Pago" INTEGER,
            "Comida_Monto" REAL,
            "Comida_Pago" INTEGER,
            "Otros_Monto" REAL,
            "Notas" TEXT
        )
    ''')
    
    # Tabla Globales
    c.execute('''CREATE TABLE IF NOT EXISTS globales 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  Pagado INTEGER, Descripcion TEXT, Monto REAL)''')

    # Tabla Detalles Otros (Límpiala de símbolos)
    c.execute('''
        CREATE TABLE IF NOT EXISTS detalles_otros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "Fecha" TEXT,
            "Categoria" TEXT,
            "Monto" REAL,
            "Pagado" INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()

# --- INICIALIZACIÓN SEGURA ---
if os.path.exists(DB_NAME):
    try:
        # Intentamos ver si la base de datos está sana
        conn = sqlite3.connect(DB_NAME)
        pd.read_sql_query("SELECT \"Traslado_Monto\" FROM itinerario LIMIT 1", conn)
        conn.close()
    except:
        # Si da error, la borramos sin piedad para resetear
        conn.close()
        os.remove(DB_NAME)


init_db() # Ahora sí, crea la estructura perfecta


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

    # --- 1. LÓGICA DE FECHAS AUTOMÁTICA (Calculamos los valores por defecto) ---
    default_ini = datetime.now().date()
    default_fin = datetime.now().date() + timedelta(days=7)
    
    if not df_it.empty:
        try:
            # Extraemos día y mes de la primera fila
            primera_fecha_str = df_it.iloc[0]["Fecha"] 
            dia = int(primera_fecha_str[:2])
            mes = int(primera_fecha_str[3:5])
            default_ini = datetime(2026, mes, dia).date()
            
            # Extraemos día y mes de la última fila
            ultima_fecha_str = df_it.iloc[-1]["Fecha"]
            dia_f = int(ultima_fecha_str[:2])
            mes_f = int(ultima_fecha_str[3:5])
            default_fin = datetime(2026, mes_f, dia_f).date()
        except:
            pass
    
    # --- 2. SIDEBAR (Aquí definimos f_ini y f_fin realmente) ---
    st.sidebar.header("⚙️ Configuración")
    f_ini = st.sidebar.date_input("Inicio", default_ini)
    f_fin = st.sidebar.date_input("Fin", default_fin)
    
    # --- 3. TÍTULO Y CONTADOR (Ahora sí podemos usar f_ini) ---
    st.title("📅 EUROVIAJE NO CENSURADO 2026")
    
    fecha_actual = datetime.now().date()
    
    if f_ini > fecha_actual:
        restante = f_ini - fecha_actual
        dias = restante.days
        st.success(f"✈️ ¡Faltan **{dias}** días para tu viaje a Europa!")
        st.caption(f"Salida programada: {f_ini.strftime('%d/%m/%Y')}")
    
    elif f_ini == fecha_actual:
        st.balloons()
        st.success("🎉 ¡EL VIAJE COMIENZA HOY! ¡A disfrutar!")
    
    else:
        if f_fin >= fecha_actual:
            st.info("🌍 Actualmente estás en tu aventura europea.")
        else:
            st.write("🏁 Este viaje ya ha finalizado.")
        
        # --- SIDEBAR ---
        st.sidebar.header("⚙️ Configuración")
        f_ini = st.sidebar.date_input("Inicio", default_ini)
        f_fin = st.sidebar.date_input("Fin", default_fin)

# Nombres técnicos (los que usará el código internamente)
cols_it = ["Fecha", "Pais", "Ciudad", "Traslado_Monto", "Traslado_Pago", 
           "Aloj_Monto", "Aloj_Pago", "Comida_Monto", "Comida_Pago", "Otros_Monto", "Notas"]

# --- 3. INICIALIZACIÓN ---
if df_it.empty:
    df_it = pd.DataFrame(columns=[
        "Fecha", "Pais", "Ciudad", "Traslado_Monto", "Traslado_Pago", 
        "Aloj_Monto", "Aloj_Pago", "Comida_Monto", "Comida_Pago", "Otros_Monto", "Notas"
    ])

if df_gl.empty:
    df_gl = pd.DataFrame(columns=["Pagado", "Descripcion", "Monto"])

if df_detalles.empty:
    # AQUÍ ESTABA EL ERROR: Solo 3 columnas técnicas
    df_detalles = pd.DataFrame(columns=["Fecha", "Categoria", "Monto", "Pagado"])

# Limpieza de tipos para evitar errores de cálculo
for df in [df_it, df_gl, df_detalles]:
    if "Monto $" in df.columns: df["Monto $"] = pd.to_numeric(df["Monto $"], errors='coerce').fillna(0.0)
    if "Pagado" in df.columns: df["Pagado"] = df["Pagado"].astype(bool)
# Limpieza de tipos segura
for c in ["Traslado_Monto", "Aloj_Monto", "Comida_Monto", "Otros_Monto"]:
    if c in df_it.columns: # <--- AGREGAR ESTO
        df_it[c] = pd.to_numeric(df_it[c], errors='coerce').fillna(0.0)

for c in ["Traslado_Pago", "Aloj_Pago", "Comida_Pago"]:
    if c in df_it.columns: # <--- AGREGAR ESTO
        df_it[c] = df_it[c].astype(bool)

# --- 4. CÁLCULOS (PRIMERO, SIN DIBUJAR NADA AÚN) ---

# 1. Presupuesto Total
base_it = df_it[["Traslado_Monto", "Aloj_Monto", "Comida_Monto"]].sum().sum()
otros_it = df_detalles["Monto"].sum() if not df_detalles.empty else 0.0
global_it = df_gl["Monto"].sum() if not df_gl.empty else 0.0

total_plan = base_it + otros_it + global_it

# 2. Ya Pagado
pag_base = (df_it.loc[df_it["Traslado_Pago"] == True, "Traslado_Monto"].sum() + 
            df_it.loc[df_it["Aloj_Pago"] == True, "Aloj_Monto"].sum() + 
            df_it.loc[df_it["Comida_Pago"] == True, "Comida_Monto"].sum())

pag_otros = df_it["Otros_Monto"].sum()
pag_global = df_gl.loc[df_gl["Pagado"] == True, "Monto"].sum() if not df_gl.empty else 0.0

total_pagado = pag_base + pag_otros + pag_global

# --- 5. SIDEBAR (ORDEN VISUAL) ---

# A. MÉTRICAS (ARRIBA DE TODO)
st.sidebar.header("💰 Resumen Financiero")
st.sidebar.metric("Presupuesto Total", f"$ {total_plan:,.2f}")
st.sidebar.metric("Ya Pagado", f"$ {total_pagado:,.2f}")
st.sidebar.metric("Pendiente", f"$ {total_plan - total_pagado:,.2f}")

st.sidebar.markdown("---")

if st.sidebar.button("Reiniciar Itinerario"):
    with st.spinner("Creando itinerario..."):
        dias = (f_fin - f_ini).days + 1
        nuevas_filas = []
        for i in range(dias):
            fecha_str = (f_ini + timedelta(days=i)).strftime("%d/%m (%a)")
            nuevas_filas.append({
                "Fecha": fecha_str, 
                "Pais": "", 
                "Ciudad": "", 
                "Traslado_Monto": 0.0, 
                "Traslado_Pago": False, 
                "Aloj_Monto": 0.0, 
                "Aloj_Pago": False, 
                "Comida_Monto": 0.0, 
                "Comida_Pago": False, 
                "Otros_Monto": 0.0, 
                "Notas": ""
            })
        
        df_it_nuevo = pd.DataFrame(nuevas_filas)
        guardar_datos_sql(df_it_nuevo, "itinerario") 
        st.success("¡Itinerario creado!")
        st.rerun()

st.sidebar.markdown("---")

# C. GESTIÓN DE DATOS / BACKUP (ABAJO DE TODO)
st.sidebar.subheader("📦 Gestión de Datos")

# Botón para descargar
with open(DB_NAME, "rb") as f:
    st.sidebar.download_button(
        label="📥 Descargar Backup (.db)",
        data=f,
        file_name="backup_viaje.db",
        mime="application/x-sqlite3"
    )

# Botón para subir (dentro de un expander para que no estorbe)
with st.sidebar.expander("📤 Restaurar Backup"):
    uploaded_db = st.file_uploader("Subir archivo previo", type="db")
    if uploaded_db:
        with open(DB_NAME, "wb") as f:
            f.write(uploaded_db.getbuffer())
        st.success("Copia restaurada correctamente.")
        st.rerun()

# --- 5. TABS ---
t1, t2, t3, t4 = st.tabs(["📅 Itinerario", "🎒 Globales", "📂 Adjuntos", "📍 Mapa"])

with t1:
    
    config_it = {
        "Traslado_Monto": st.column_config.NumberColumn("Traslado $", format="$ %.2f"),
        "Traslado_Pago": st.column_config.CheckboxColumn("P. Traslado"),
        "Aloj_Monto": st.column_config.NumberColumn("Aloj. $", format="$ %.2f"),
        "Aloj_Pago": st.column_config.CheckboxColumn("P. Aloj"),
        "Comida_Monto": st.column_config.NumberColumn("Comida $", format="$ %.2f"),
        "Comida_Pago": st.column_config.CheckboxColumn("P. Comida"),
        "Otros_Monto": st.column_config.NumberColumn("Otros (Pagado) $", format="$ %.2f", disabled=True),
        "Pais": st.column_config.TextColumn("País"),
        "Notas": st.column_config.TextColumn("Notas", width="large")
    }
    
    df_it_edit = st.data_editor(df_it, num_rows="dynamic", width="stretch", 
                                hide_index=True, column_config=config_it)
    
    if not df_it_edit.equals(df_it):
        guardar_datos_sql(df_it_edit, "itinerario")
        st.rerun()

# --- DENTRO DE WITH T1 ---
st.markdown("---")
st.subheader("🕵️ Detalle de Otros gastos")

lista_fechas = df_it_edit["Fecha"].tolist()
dia_sel = st.selectbox("Día para detallar:", lista_fechas)

# 1. Filtramos asegurando que solo traemos las 3 columnas de datos
det_dia = df_detalles[df_detalles["Fecha"] == dia_sel][["Categoria", "Monto", "Pagado"]].reset_index(drop=True)

# 2. Configuración visual (Traducción de nombres)
config_det = {
    "Categoria": st.column_config.TextColumn("Categoría/Descripción"),
    "Monto": st.column_config.NumberColumn("Monto $", format="$ %.2f"),
    "Pagado": st.column_config.CheckboxColumn("¿Pagado?")
}

det_edit = st.data_editor(
    det_dia, 
    num_rows="dynamic", 
    width="stretch", 
    hide_index=True,
    column_config=config_det,
    key=f"ed_{dia_sel}"
)

if not det_edit.equals(det_dia):
    # 1. Reconstruimos el DataFrame de detalles con los nuevos datos
    otros_dias = df_detalles[df_detalles["Fecha"] != dia_sel]
    nuevo_dia = det_edit.copy()
    nuevo_dia["Fecha"] = dia_sel
    
    df_detalles_nuevo = pd.concat([otros_dias, nuevo_dia], ignore_index=True)
    
    # 2. CALCULAMOS EL TOTAL (Solo lo pagado)
    # Importante: Usamos 'Monto' y 'Pagado' (nombres técnicos de tu DB)
    total_dia = det_edit.loc[det_edit["Pagado"] == True, "Monto"].sum()
    
    # 3. IMPACTAMOS EL ITINERARIO (La tabla que ves arriba)
    # Buscamos la fila exacta y actualizamos la columna técnica
    df_it.loc[df_it["Fecha"] == dia_sel, "Otros_Monto"] = total_dia
    
    # 4. GUARDADO DOBLE EN SQL
    guardar_datos_sql(df_detalles_nuevo, "detalles_otros")
    guardar_datos_sql(df_it, "itinerario") # <--- Esto es vital
    
    # 5. RECARGA PARA MOSTRAR CAMBIOS
    st.rerun()
    
with t2:
    st.subheader("🎒 Gastos Globales")
    
    # Configuración visual para que tú veas nombres bonitos
    config_gl = {
        "Pagado": st.column_config.CheckboxColumn("¿Pagado?"),
        "Descripcion": st.column_config.TextColumn("Descripción"),
        "Monto": st.column_config.NumberColumn("Monto $", format="$ %.2f")
    }

    # Aseguramos que el editor use los nombres técnicos (Monto, Descripcion)
    df_gl_edit = st.data_editor(
        df_gl, 
        num_rows="dynamic", 
        width="stretch", 
        hide_index=True,
        column_config=config_gl
    )

    if not df_gl_edit.equals(df_gl):
        # GUARDADO CLAVE: Usamos el nombre de tabla en minúsculas
        guardar_datos_sql(df_gl_edit, "globales")
        st.rerun()

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
    # Verificamos que las columnas existan antes de filtrar
    if "Ciudad" in df_it_edit.columns and "Pais" in df_it_edit.columns:
        df_m = df_it_edit[(df_it_edit["Ciudad"] != "") & (df_it_edit["Pais"] != "")].copy()
        puntos = []
        for _, r in df_m.iterrows():
            c = obtener_coordenadas(r["Ciudad"], r["Pais"])
            if c: puntos.append({"lat": c[0], "lon": c[1], "name": r["Ciudad"]})
        
        if len(puntos) >= 2:
            df_p = pd.DataFrame(puntos)
            rutas = [{"start": [puntos[i]["lon"], puntos[i]["lat"]], "end": [puntos[i+1]["lon"], puntos[i+1]["lat"]]} for i in range(len(puntos)-1)]
            st.pydeck_chart(pdk.Deck(
                map_style='light', 
                initial_view_state=pdk.ViewState(latitude=df_p["lat"].mean(), longitude=df_p["lon"].mean(), zoom=3, pitch=45),
                layers=[
                    pdk.Layer("ArcLayer", rutas, get_source_position="start", get_target_position="end", get_width=3, get_tilt=15),
                    pdk.Layer("ScatterplotLayer", df_p, get_position="[lon, lat]", get_radius=20000, get_color="[200, 30, 0]")
                ]
            ))
    else:
        st.warning("Asegúrate de que las columnas 'Ciudad' y 'Pais' estén configuradas.")

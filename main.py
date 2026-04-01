import streamlit as st
import pandas as pd
import os
import pydeck as pdk
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Europa 2026 Pro", layout="wide")
FOLDER_ADJUNTOS = "mis_adjuntos"
if not os.path.exists(FOLDER_ADJUNTOS):
    os.makedirs(FOLDER_ADJUNTOS)

# --- CONEXIÓN ---
conn = st.connection("gsheets", type=GSheetsConnection)

# DEPUREMOS DE FORMA MÁS SIMPLE
if "connections" not in st.secrets:
    st.error("❌ Streamlit no encuentra la sección [connections] en los Secrets.")
elif "gsheets" not in st.secrets.connections:
    st.error("❌ Streamlit no encuentra la sección [gsheets] dentro de connections.")
elif "private_key" not in st.secrets.connections.gsheets:
    st.error("❌ Streamlit encuentra gsheets pero NO la private_key.")
else:
    st.success("✅ ¡Credenciales detectadas correctamente!")

@st.cache_data(ttl=600)
def cargar_datos(nombre_hoja):
    try:
        # Intentamos leer la hoja
        df = conn.read(worksheet=nombre_hoja, ttl="10m")
        if df is None or df.empty:
            raise ValueError("Hoja vacía")
        return df
    except Exception as e:
        # SI FALLA EL 404, CREAMOS LAS COLUMNAS PARA QUE EL RESTO DEL CÓDIGO NO EXPLOTE
        if nombre_hoja == "Itinerario":
            return pd.DataFrame(columns=["Fecha", "País", "Ciudad", "Traslado $", "P. Traslado", "Aloj. $", "P. Aloj", "Comida $", "P. Comida", "Otros $", "Notas"])
        elif nombre_hoja == "Globales":
            return pd.DataFrame(columns=["Pagado", "Descripción", "Monto $"])
        else:
            return pd.DataFrame(columns=["Fecha", "Categoría/Descripción", "Monto $", "Pagado"])

def guardar_en_google(df, nombre_hoja):
    try:
        # 1. Limpiar el DataFrame para que Google lo acepte
        df_save = df.copy()
        
        # 2. Intentar la actualización
        conn.update(worksheet=nombre_hoja, data=df_save)
        
        # 3. Limpiar caché para que la App vea los cambios
        st.cache_data.clear()
        st.toast(f"✅ ¡Datos guardados en {nombre_hoja}!")
    except Exception as e:
        # Si da 404, imprimimos un mensaje más claro
        if "404" in str(e):
            st.error(f"❌ Error 404: No existe la pestaña '{nombre_hoja}' en tu Google Sheets.")
        else:
            st.error(f"❌ Error al guardar: {e}")

@st.cache_data
def obtener_coordenadas(ciudad, pais):
    try:
        geolocator = Nominatim(user_agent="itinerario_v26")
        location = geolocator.geocode(f"{ciudad}, {pais}")
        if location: return [location.latitude, location.longitude]
    except: return None

# --- 3. INICIALIZACIÓN DE DATOS (Corregido) ---
df_it = cargar_datos("Itinerario")
df_gl = cargar_datos("Globales")
df_detalles = cargar_datos("Detalles_Otros")

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
st.sidebar.header("⚙️ Configuración")
f_ini = st.sidebar.date_input("Inicio", datetime.now())
f_fin = st.sidebar.date_input("Fin", datetime.now() + timedelta(days=7))

if st.sidebar.button("Reiniciar Itinerario"):
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
    
    # Intentar guardar y SOLO si tiene éxito, reiniciar la app
    guardar_en_google(df_it_nuevo, "Itinerario")
    st.info("Itinerario creado. Recargando...")
    st.rerun()

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

    st.markdown("---")
    dia_sel = st.selectbox("Detallar Otros:", df_it_edit["Fecha"].tolist())
    det_dia = df_detalles[df_detalles["Fecha"] == dia_sel].drop(columns=["Fecha"]).reset_index(drop=True)
    det_edit = st.data_editor(det_dia, num_rows="dynamic", width="stretch", hide_index=True)
    
    if not det_edit.equals(det_dia):
        df_detalles = pd.concat([df_detalles[df_detalles["Fecha"] != dia_sel], det_edit.assign(Fecha=dia_sel)], ignore_index=True)
        guardar_en_google(df_detalles, "Detalles_Otros")
        df_it_edit.loc[df_it_edit["Fecha"] == dia_sel, "Otros $"] = det_edit.loc[det_edit["Pagado"], "Monto $"].sum()
        guardar_en_google(df_it_edit, "Itinerario"); st.rerun()

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

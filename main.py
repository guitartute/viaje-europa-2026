import streamlit as st
import pandas as pd
import os
import pydeck as pdk
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# --- 1. CONFIGURACIÓN Y ARCHIVOS ---
st.set_page_config(page_title="Europa 2026 Pro", layout="wide")
FILE_ITINERARIO = "itinerario_europa.csv"
FILE_GLOBALES = "gastos_globales.csv"
FILE_DETALLES = "detalles_otros.csv"
FOLDER_ADJUNTOS = "mis_adjuntos"

if not os.path.exists(FOLDER_ADJUNTOS):
    os.makedirs(FOLDER_ADJUNTOS)

# --- CONFIGURACIÓN DE CONEXIÓN ---
# En Streamlit Cloud, pondremos las credenciales en "Secrets"
conn = st.connection("gsheets", type=GSheetsConnection)

def cargar_desde_google(nombre_hoja):
    try:
        # Intenta leer la pestaña específica
        return conn.read(worksheet=nombre_hoja, ttl="0")
    except:
        # Si no existe, devuelve un DataFrame vacío con las columnas correctas
        return pd.DataFrame()

# --- REEMPLAZO EN TU LÓGICA DE GUARDADO ---
def guardar_en_google(df, nombre_hoja):
    conn.update(worksheet=nombre_hoja, data=df)
    st.success(f"Datos sincronizados en Google Sheets ({nombre_hoja})")

def cargar_detalles():
    if os.path.exists(FILE_DETALLES):
        df = pd.read_csv(FILE_DETALLES)
        df["Monto $"] = pd.to_numeric(df["Monto $"], errors='coerce').fillna(0.0)
        df["Pagado"] = df["Pagado"].astype(bool)
        df["Categoría/Descripción"] = df["Categoría/Descripción"].astype(str).replace("nan", "")
        return df
    return pd.DataFrame(columns=["Fecha", "Categoría/Descripción", "Monto $", "Pagado"])

@st.cache_data
def obtener_coordenadas(ciudad, pais):
    try:
        geolocator = Nominatim(user_agent="itinerario_v26")
        location = geolocator.geocode(f"{ciudad}, {pais}")
        if location: return [location.latitude, location.longitude]
    except: return None
    return None

# --- 3. INICIALIZACIÓN DE DATOS ---
df_it = cargar_datos()
df_detalles = cargar_detalles()
df_gl = pd.read_csv(FILE_GLOBALES) if os.path.exists(FILE_GLOBALES) else pd.DataFrame(columns=["Pagado", "Descripción", "Monto $"])

# --- 4. BARRA LATERAL (SIDEBAR) Y CÁLCULOS ---
st.sidebar.header("⚙️ Configuración")
f_ini = st.sidebar.date_input("Inicio", datetime.now())
f_fin = st.sidebar.date_input("Fin", datetime.now() + timedelta(days=7))

if st.sidebar.button("Reiniciar Itinerario"):
    dias = (f_fin - f_ini).days + 1
    nuevas_filas = [{"Fecha": (f_ini + timedelta(days=i)).strftime("%d/%m (%a)"), 
                     "País": "", "Ciudad": "", "Traslado $": 0.0, "P. Traslado": False,
                     "Aloj. $": 0.0, "P. Aloj": False, "Comida $": 0.0, "P. Comida": False,
                     "Otros $": 0.0, "Notas": ""} for i in range(dias)]
    df_it = pd.DataFrame(nuevas_filas)
    guardar_datos(df_it, df_gl)
    st.rerun()

# LÓGICA DE PRESUPUESTO
plan_base = df_it["Traslado $"].sum() + df_it["Aloj. $"].sum() + df_it["Comida $"].sum()
plan_otros = df_detalles["Monto $"].sum()
plan_global = df_gl["Monto $"].sum() if not df_gl.empty else 0
total_plan = plan_base + plan_otros + plan_global

pag_base = (df_it.loc[df_it["P. Traslado"], "Traslado $"].sum() + 
            df_it.loc[df_it["P. Aloj"], "Aloj. $"].sum() + 
            df_it.loc[df_it["P. Comida"], "Comida $"].sum())
total_pag = pag_base + df_it["Otros $"].sum() + (df_gl.loc[df_gl["Pagado"]==True, "Monto $"].sum() if not df_gl.empty else 0)

st.sidebar.markdown("---")
st.sidebar.metric("Presupuesto Total", f"$ {total_plan:,.2f}")
st.sidebar.metric("Ya Pagado", f"$ {total_pag:,.2f}")
st.sidebar.metric("Pendiente", f"$ {total_plan - total_pag:,.2f}", delta_color="inverse")

# --- 5. CUERPO PRINCIPAL ---
st.title("🌍 Mi Viaje a Europa 2026")
t1, t2, t3, t4 = st.tabs(["📅 Itinerario", "🎒 Globales", "📂 Adjuntos", "📍 Mapa"])

with t1:
    df_it_edit = st.data_editor(df_it, num_rows="dynamic", width="stretch", hide_index=True,
        column_config={"Otros $": st.column_config.NumberColumn("Otros $ (Pagado)", disabled=True, format="$ %.2f")})
    if not df_it_edit.equals(df_it):
        guardar_datos(df_it_edit, df_gl); st.rerun()

    st.markdown("---")
    st.subheader("🕵️ Desglose de 'Otros'")
    dia_sel = st.selectbox("Día para detallar:", df_it_edit["Fecha"].tolist())
    det_dia = df_detalles[df_detalles["Fecha"] == dia_sel].drop(columns=["Fecha"]).reset_index(drop=True)
    
    det_edit = st.data_editor(det_dia, num_rows="dynamic", width="stretch", hide_index=True,
        column_config={"Categoría/Descripción": st.column_config.TextColumn("Descripción"),
                       "Monto $": st.column_config.NumberColumn(format="$ %.2f")})
    
    if not det_edit.equals(det_dia):
        df_detalles = pd.concat([df_detalles[df_detalles["Fecha"] != dia_sel], det_edit.assign(Fecha=dia_sel)], ignore_index=True)
        df_detalles.to_csv(FILE_DETALLES, index=False)
        df_it_edit.loc[df_it_edit["Fecha"] == dia_sel, "Otros $"] = det_edit.loc[det_edit["Pagado"]==True, "Monto $"].sum()
        guardar_datos(df_it_edit, df_gl); st.rerun()

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
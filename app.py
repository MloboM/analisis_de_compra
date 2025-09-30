# app.py
import streamlit as st
import pandas as pd
from pathlib import Path
import os

from analisis_core import analizar, DEFAULTS

st.set_page_config(page_title="Análisis de Compras", page_icon="📦", layout="centered")

st.title("📦 Análisis de Compras")
st.caption("Sube tus archivos de ventas e inventario (CSV o Excel), ajusta parámetros y descarga/guarda el Excel de resultados.")

# --------- Selección de tipo de archivo ---------
tipo_archivo = st.radio("Tipo de archivo a utilizar:", ["CSV", "Excel (.xlsx)"], horizontal=True)

col1, col2 = st.columns(2)
with col1:
    ventas_file = st.file_uploader("Archivo de **Ventas**", type=("csv","xlsx") if tipo_archivo=="Excel (.xlsx)" else ("csv",))
with col2:
    inventario_file = st.file_uploader("Archivo de **Inventario**", type=("csv","xlsx") if tipo_archivo=="Excel (.xlsx)" else ("csv",))

# --------- Parámetros ----------
st.subheader("Parámetros")
c1, c2, c3 = st.columns(3)
with c1:
    lead_time = st.number_input("Lead Time (días)", min_value=0, value=DEFAULTS["LEAD_TIME_DIAS"])
with c2:
    cobertura = st.number_input("Cobertura (meses)", min_value=0, value=DEFAULTS["COBERTURA_MESES"])
with c3:
    dias_semana = st.number_input("Días de venta/semana", min_value=1, max_value=7, value=DEFAULTS["VENTA_DIAS_SEMANA"])

with st.expander("Opciones avanzadas"):
    z = st.number_input("Z (nivel de servicio ~95% → 1.65)", min_value=0.0, value=DEFAULTS["Z"])
    c1a, c2a = st.columns(2)
    with c1a:
        abc_a = st.number_input("Umbral A (ABC)", min_value=0.0, max_value=1.0, value=DEFAULTS["ABC_UMBRAL_A"])
        xyz_x = st.number_input("Umbral X (CV)", min_value=0.0, max_value=1.0, value=DEFAULTS["XYZ_UMBRAL_X"])
    with c2a:
        abc_b = st.number_input("Umbral B (ABC)", min_value=0.0, max_value=1.0, value=DEFAULTS["ABC_UMBRAL_B"])
        xyz_y = st.number_input("Umbral Y (CV)", min_value=0.0, max_value=1.0, value=DEFAULTS["XYZ_UMBRAL_Y"])

st.markdown("---")

# --------- Utilidades de lectura ----------
def leer_df(file, tipo):
    if file is None:
        return None
    try:
        if tipo == "CSV":
            return pd.read_csv(file, encoding="utf-8-sig")
        else:
            return pd.read_excel(file)  # si hay varias hojas, puedes agregar sheet_name=
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return None

# --------- Botón Ejecutar ----------
ejecutar = st.button("🚀 Ejecutar análisis")

if ejecutar:
    if ventas_file is None or inventario_file is None:
        st.warning("Por favor, sube **ambos** archivos (Ventas e Inventario).")
    else:
        df_ventas = leer_df(ventas_file, "CSV" if tipo_archivo=="CSV" else "Excel")
        df_inv = leer_df(inventario_file, "CSV" if tipo_archivo=="CSV" else "Excel")

        if df_ventas is not None and df_inv is not None:
            with st.spinner("Procesando…"):
                try:
                    excel_bytes = analizar(
                        df_ventas, df_inv,
                        LEAD_TIME_DIAS=int(lead_time),
                        COBERTURA_MESES=int(cobertura),
                        VENTA_DIAS_SEMANA=int(dias_semana),
                        Z=float(z),
                        ABC_UMBRAL_A=float(abc_a),
                        ABC_UMBRAL_B=float(abc_b),
                        XYZ_UMBRAL_X=float(xyz_x),
                        XYZ_UMBRAL_Y=float(xyz_y),
                    )
                    st.success("¡Listo!")

                    # ===== Opción A: Descargar por navegador =====
                    st.download_button(
                        label="⬇️ Descargar resultado_analisis_compras.xlsx",
                        data=excel_bytes,
                        file_name="resultado_analisis_compras.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

                    # ===== Opción B: Guardar en disco (con carpeta por defecto Descargas) =====
                    st.markdown("### 💾 Guardar en mi PC")

                    # Carpeta Descargas por defecto (Windows/Linux/macOS)
                    default_downloads = Path.home() / "Downloads"
                    # En algunos entornos corporativos puede variar; se puede editar aquí si fuera necesario.

                    colp1, colp2 = st.columns([3,2])
                    with colp1:
                        carpeta_destino = st.text_input(
                            "Carpeta de destino",
                            value=str(default_downloads),
                            help="Puedes cambiarla si quieres guardar en otra ruta."
                        )
                    with colp2:
                        nombre_archivo = st.text_input(
                            "Nombre del archivo",
                            value="resultado_analisis_compras.xlsx"
                        )

                    if st.button("💾 Guardar en mi PC"):
                        try:
                            carpeta = Path(carpeta_destino).expanduser()
                            carpeta.mkdir(parents=True, exist_ok=True)
                            destino = carpeta / nombre_archivo
                            with open(destino, "wb") as f:
                                f.write(excel_bytes.getbuffer())
                            st.success(f"Archivo guardado en: {destino}")
                        except Exception as e:
                            st.error(f"No se pudo guardar el archivo: {e}")

                except Exception as e:
                    st.error(f"Ocurrió un error durante el análisis: {e}")

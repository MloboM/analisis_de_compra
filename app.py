import streamlit as st
import pandas as pd
from pathlib import Path
from analisis_core import analizar, DEFAULTS

st.set_page_config(page_title="Análisis de Compras", page_icon="📦", layout="centered")

st.title("📦 Análisis de Compras")
st.caption("Sube tus archivos de ventas e inventario (CSV o Excel) y descarga el análisis en Excel.")

# --------- Carga de archivos ---------
col1, col2 = st.columns(2)
with col1:
    ventas_file = st.file_uploader("Archivo de **Ventas** (transaccional)", type=("csv","xlsx"))
with col2:
    inventario_file = st.file_uploader("Archivo de **Inventario**", type=("csv","xlsx"))

# --------- Parámetros ----------
st.subheader("Parámetros")
c1, c2, c3 = st.columns(3)
with c1:
    lead_time = st.number_input("Lead Time (días)", min_value=0.0, value=float(DEFAULTS["LEAD_TIME_DIAS"]))
with c2:
    cobertura = st.number_input("Cobertura (meses)", min_value=0.0, value=float(DEFAULTS["COBERTURA_MESES"]), step=0.5)
with c3:
    dias_semana = st.number_input("Días de venta/semana", min_value=1, max_value=7, value=int(DEFAULTS["VENTA_DIAS_SEMANA"]))

st.subheader("Clasificación XYZ (variabilidad)")
c1x, c2x, c3x = st.columns(3)
with c1x:
    x_th = st.number_input("X (≤0.30) Estables", min_value=0.0, max_value=1.0, value=DEFAULTS["XYZ_UMBRAL_X"], key="x_th")
with c2x:
    y_th = st.number_input("Y (≤0.60) Moderadamente variables", min_value=0.0, max_value=1.0, value=DEFAULTS["XYZ_UMBRAL_Y"], key="y_th")
with c3x:
    st.markdown("**Z (Erráticos)**: CV > Y")

if y_th <= x_th:
    st.warning("Y debe ser mayor que X. Ajusté Y a X + 0.05.")
    y_th = round(x_th + 0.05, 2)

st.markdown("---")

# --------- Botón Ejecutar ----------
if st.button("🚀 Ejecutar análisis"):
    if ventas_file is None or inventario_file is None:
        st.warning("Por favor, sube **ambos** archivos.")
    else:
        try:
            df_ventas = pd.read_csv(ventas_file) if ventas_file.name.endswith(".csv") else pd.read_excel(ventas_file)
            df_inv = pd.read_csv(inventario_file) if inventario_file.name.endswith(".csv") else pd.read_excel(inventario_file)

            with st.spinner("Procesando…"):
                excel_bytes = analizar(
                    df_ventas, df_inv,
                    LEAD_TIME_DIAS=float(lead_time),
                    COBERTURA_MESES=float(cobertura),
                    VENTA_DIAS_SEMANA=int(dias_semana),
                    XYZ_UMBRAL_X=float(x_th),
                    XYZ_UMBRAL_Y=float(y_th),
                )

            st.success("¡Listo!")
            st.download_button(
                label="⬇️ Descargar resultado_analisis_compras.xlsx",
                data=excel_bytes,
                file_name="resultado_analisis_compras.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            # Opción de guardar localmente (carpeta Descargas por defecto)
            st.markdown("### 💾 Guardar en mi PC")
            default_downloads = Path.home() / "Downloads"
            colp1, colp2 = st.columns([3,2])
            with colp1:
                carpeta_destino = st.text_input("Carpeta de destino", value=str(default_downloads))
            with colp2:
                nombre_archivo = st.text_input("Nombre del archivo", value="resultado_analisis_compras.xlsx")

            if st.button("💾 Guardar"):
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



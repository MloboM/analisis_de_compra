# Importaciones optimizadas y organizadas
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# Importaciones locales
from analisis_core import analizar, DEFAULTS
from analisis_cliente import (
    validar_columnas_cliente,
    analizar_clientes,
    analizar_productos_cliente,
    identificar_alertas_cliente,
    calcular_evolucion_cliente
)

# Configuración de Streamlit
st.set_page_config(
    page_title="Análisis Inteligente de Compras",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
    <style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0 0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #667eea;
        color: white;
    }
    div[data-testid="stMetricValue"] {
        font-size: 28px;
    }
    </style>
""", unsafe_allow_html=True)

# Inicialización de estados de sesión
def inicializar_estados_sesion():
    """
    Inicializa los estados de sesión necesarios para la aplicación.
    Evita múltiples verificaciones repetitivas en el código.
    """
    estados = [
        'df_resultado', 
        'excel_bytes', 
        'analisis_clientes', 
        'df_ventas_original', 
        'df_inventario_original'
    ]
    for estado in estados:
        if estado not in st.session_state:
            st.session_state[estado] = None

# Llamada a la inicialización de estados
inicializar_estados_sesion()

# Header principal de la aplicación
st.title("🏦 Sistema Inteligente de Análisis de Compras")
st.markdown("**Optimiza tu inventario con análisis ABC-XYZ y predicción de demanda**")

# Sidebar para configuración y carga de archivos
with st.sidebar:
    # Añadir tabs de navegación
    tab_config, tab_archivos, tab_parametros = st.tabs([
        "⚙️ Configuración", 
        "📂 Archivos", 
        "🎯 Parámetros"
    ])

    # Tab de Archivos
    with tab_archivos:
        st.header("📂 Archivos de entrada")
        
        ventas_file = st.file_uploader(
            "Ventas (transaccional)",
            type=("csv", "xlsx"),
            help="Debe contener: COD_PROD, Fecha, Cantidad, PRECIO_DESCUENTO. Opcional: NOM_CLIENTE, DES_PROVEEDOR"
        )
        inventario_file = st.file_uploader(
            "Inventario actual",
            type=("csv", "xlsx"),
            help="Debe contener: COD_PROD, Inventario.DESCRIPCION, SALDO ACTUAL"
        )

    # Tab de Parámetros
    with tab_parametros:
        st.header("🎯 Parámetros de análisis")
        
        # Configuración de inventario
        with st.expander("Configuración de inventario", expanded=True):
            lead_time = st.number_input(
                "Lead Time (días)",
                min_value=0.0,
                value=float(DEFAULTS["LEAD_TIME_DIAS"]),
                help="Tiempo de reabastecimiento desde el pedido"
            )
            cobertura = st.number_input(
                "Cobertura deseada (meses)",
                min_value=0.0,
                value=float(DEFAULTS["COBERTURA_MESES"]),
                step=0.5,
                help="Meses de inventario que deseas mantener"
            )
            dias_semana = st.number_input(
                "Días de venta/semana",
                min_value=1,
                max_value=7,
                value=int(DEFAULTS["VENTA_DIAS_SEMANA"])
            )
        
        # Clasificación XYZ
        with st.expander("Clasificación XYZ (variabilidad)"):
            x_th = st.slider(
                "Umbral X (Estables)",
                0.0, 1.0, DEFAULTS["XYZ_UMBRAL_X"],
                help="CV ≤ este valor = productos estables"
            )
            y_th = st.slider(
                "Umbral Y (Moderados)",
                0.0, 1.0, DEFAULTS["XYZ_UMBRAL_Y"],
                help="CV entre X e Y = variabilidad moderada"
            )
            
            # Validación de umbrales
            if y_th <= x_th:
                st.warning("⚠️ Umbral Y debe ser mayor que umbral X")
                y_th = round(x_th + 0.05, 2)
            
            st.info(f"**Z (Erráticos)**: CV > {y_th}")
        
        st.markdown("---")
        
        # Botón de ejecución
        ejecutar = st.button("🚀 Ejecutar Análisis", type="primary")

# Procesamiento principal
if ejecutar:
    # Validación de archivos cargados
    if ventas_file is None or inventario_file is None:
        st.error("⚠️ Por favor, sube ambos archivos (ventas e inventario)")
    else:
        try:
            # Spinner de procesamiento
            with st.spinner("📄 Procesando datos..."):
                # Leer archivos con detección automática de formato
                df_ventas = pd.read_csv(ventas_file, encoding='utf-8-sig') if ventas_file.name.endswith(".csv") else pd.read_excel(ventas_file)
                df_inv = pd.read_csv(inventario_file, encoding='utf-8-sig') if inventario_file.name.endswith(".csv") else pd.read_excel(inventario_file)

                # Ejecutar análisis principal
                excel_bytes = analizar(
                    df_ventas, df_inv,
                    LEAD_TIME_DIAS=float(lead_time),
                    COBERTURA_MESES=float(cobertura),
                    VENTA_DIAS_SEMANA=int(dias_semana),
                    XYZ_UMBRAL_X=float(x_th),
                    XYZ_UMBRAL_Y=float(y_th),
                )
                
                # Leer Excel generado
                excel_bytes.seek(0)
                df_resultado = pd.read_excel(excel_bytes, sheet_name="Analisis")
                
                # Guardar resultados en sesión
                st.session_state.df_resultado = df_resultado
                excel_bytes.seek(0)
                st.session_state.excel_bytes = excel_bytes
                
                # Guardar DataFrames originales
                st.session_state.df_ventas_original = df_ventas.copy()
                st.session_state.df_inventario_original = df_inv.copy()
                
                # Análisis por cliente
                try:
                    analisis_clientes_result = analizar_clientes(
                        df_ventas, 
                        df_inv
                    )
                    st.session_state.analisis_clientes = analisis_clientes_result
                except Exception as e:
                    st.warning(f"No se pudo realizar análisis por cliente: {e}")
                    st.session_state.analisis_clientes = None
            
            # Mensaje de éxito
            st.success("✅ Análisis completado exitosamente!")
            
        except Exception as e:
            st.error(f"❌ Error durante el análisis: {e}")
            st.exception(e)

# Procesamiento de resultados si existen
if st.session_state.df_resultado is not None:
    df = st.session_state.df_resultado
    
    # Identificar columnas de meses
    todas_cols = list(df.columns)
    meses_cols = [c for c in todas_cols if '-' in str(c) and len(str(c).split('-')) == 2]
    
    # Definición de tabs principales
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard Ejecutivo",
        "📋 Análisis Resumido",
        "📈 Gráficos y Tendencias",
        "👥 Análisis por Cliente",
        "💾 Exportar Datos"
    ])
    # TAB 1: Dashboard Ejecutivo
    with tab1:
        st.header("Resumen Ejecutivo")
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_productos = len(df)
            st.metric("Total Productos", f"{total_productos:,}")
        
        with col2:
            productos_falta = len(df[df['ESTADO'] == 'FALTA INV.'])
            pct_falta = (productos_falta / total_productos * 100) if total_productos > 0 else 0
            st.metric(
                "Productos con Falta",
                f"{productos_falta:,}",
                f"{pct_falta:.1f}%",
                delta_color="inverse"
            )
        
        with col3:
            # Productos con sobrestock (SALDO_ACTUAL > INV_OBJETIVO)
            productos_sobrestock = len(df[df['SALDO_ACTUAL'] > df['INV_OBJETIVO']])
            pct_sobrestock = (productos_sobrestock / total_productos * 100) if total_productos > 0 else 0
            st.metric(
                "Productos con Sobrestock",
                f"{productos_sobrestock:,}",
                f"{pct_sobrestock:.1f}%",
                delta_color="inverse"
            )
        
        with col4:
            total_comprar = df['CANT_A_COMPRAR'].sum()
            st.metric("Unidades a Comprar", f"{total_comprar:,.0f}")
        
        st.markdown("---")
        
        # Distribución ABC-XYZ
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Distribución ABC (Valor)")
            abc_counts = df['ABC'].value_counts().sort_index()
            fig_abc = px.pie(
                values=abc_counts.values,
                names=abc_counts.index,
                title="Clasificación por Valor de Ventas",
                color=abc_counts.index,
                color_discrete_map={'A': '#00cc96', 'B': '#ffa15a', 'C': '#ef553b'},
                hole=0.4
            )
            fig_abc.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_abc, width='stretch')
        
        with col2:
            st.subheader("Distribución XYZ (Variabilidad)")
            xyz_counts = df['XYZ'].value_counts().sort_index()
            fig_xyz = px.pie(
                values=xyz_counts.values,
                names=xyz_counts.index,
                title="Clasificación por Variabilidad",
                color=xyz_counts.index,
                color_discrete_map={'X': '#636efa', 'Y': '#ab63fa', 'Z': '#ff6692'},
                hole=0.4
            )
            fig_xyz.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_xyz, width='stretch')
        
        # Matriz ABC-XYZ
        st.subheader("Matriz ABC-XYZ")
        matriz = df.groupby(['ABC', 'XYZ']).size().reset_index(name='Cantidad')
        fig_matriz = px.density_heatmap(
            matriz, x='XYZ', y='ABC',
            z='Cantidad',
            title="Distribución de Productos en Matriz ABC-XYZ",
            color_continuous_scale='Viridis',
            text_auto=True
        )
        fig_matriz.update_layout(height=400)
        st.plotly_chart(fig_matriz, width='stretch')
        
        # Top productos críticos
        st.subheader("🚨 Top 10 Productos Críticos (Mayor Falta de Inventario)")
        df_criticos = df[df['ESTADO'] == 'FALTA INV.'].nlargest(10, 'CANT_A_COMPRAR')
        if len(df_criticos) > 0:
            fig_criticos = px.bar(
                df_criticos,
                x='CANT_A_COMPRAR',
                y='COD_PROD',
                orientation='h',
                title="Productos que requieren compra urgente",
                labels={'CANT_A_COMPRAR': 'Cantidad a Comprar', 'COD_PROD': 'Código Producto'},
                color='ABC_XYZ',
                text='CANT_A_COMPRAR'
            )
            fig_criticos.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            fig_criticos.update_layout(height=500, showlegend=True)
            st.plotly_chart(fig_criticos, width='stretch')
        else:
            st.info("✅ No hay productos con falta de inventario")
            # Nueva sección: Análisis de Sobrestock
        st.subheader("📦 Análisis de Sobrestock")
        
        # Calcular métricas de sobrestock
        df['EXCESO_INVENTARIO'] = (df['SALDO_ACTUAL'] - df['INV_OBJETIVO']).clip(lower=0)
        df['COBERTURA_MESES'] = df['SALDO_ACTUAL'] / df['PROM_12M'].replace(0, np.nan)
        df['TIENE_SOBRESTOCK'] = df['SALDO_ACTUAL'] > df['INV_OBJETIVO']
        
        df_sobrestock = df[df['TIENE_SOBRESTOCK']].copy()
        
        if len(df_sobrestock) > 0:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                unidades_exceso = df_sobrestock['EXCESO_INVENTARIO'].sum()
                st.metric("Unidades en Exceso", f"{unidades_exceso:,.0f}")
            
            with col2:
                valor_inmovilizado = df_sobrestock['VALOR_VENTAS_12M'].sum()
                # Formato para Costa Rica: millares con punto, decimales con coma
                valor_formateado = f"₡{valor_inmovilizado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.metric("Valor Inmovilizado (12M)", valor_formateado)
            
            with col3:
                cobertura_prom = df_sobrestock['COBERTURA_MESES'].mean()
                st.metric("Cobertura Promedio", f"{cobertura_prom:.1f} meses")
                
            # Gráfico de sobrestock por clasificación ABC
            col1, col2 = st.columns(2)
            
            with col1:
                fig_sobre_abc = px.bar(
                    df_sobrestock.groupby('ABC')['EXCESO_INVENTARIO'].sum().reset_index(),
                    x='ABC',
                    y='EXCESO_INVENTARIO',
                    title="Unidades en Exceso por Clasificación ABC",
                    color='ABC',
                    color_discrete_map={'A': '#ef553b', 'B': '#ffa15a', 'C': '#00cc96'},
                    text='EXCESO_INVENTARIO'
                )
                fig_sobre_abc.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                fig_sobre_abc.update_layout(showlegend=False)
                st.plotly_chart(fig_sobre_abc, width='stretch')
            
            with col2:
                # Distribución de cobertura
                fig_cobertura = px.histogram(
                    df_sobrestock,
                    x='COBERTURA_MESES',
                    nbins=20,
                    title="Distribución de Meses de Cobertura (Sobrestock)",
                    labels={'COBERTURA_MESES': 'Meses de Cobertura', 'count': 'Cantidad de Productos'},
                    color_discrete_sequence=['#ff6692']
                )
                fig_cobertura.add_vline(x=1.0, line_dash="dash", line_color="red", 
                                       annotation_text="Objetivo (puede variar)")
                st.plotly_chart(fig_cobertura, width='stretch')
                # Top 10 productos con mayor sobrestock
            st.markdown("#### 🔴 Top 10 Productos con Mayor Sobrestock")
            df_top_sobre = df_sobrestock.nlargest(10, 'EXCESO_INVENTARIO')[
                ['COD_PROD', 'DESCRIPCION', 'ABC_XYZ', 'SALDO_ACTUAL', 'INV_OBJETIVO', 
                 'EXCESO_INVENTARIO', 'COBERTURA_MESES', 'PROM_12M']
            ].copy()
            
            df_top_sobre['COBERTURA_MESES'] = df_top_sobre['COBERTURA_MESES'].round(2)
            df_top_sobre['EXCESO_INVENTARIO'] = df_top_sobre['EXCESO_INVENTARIO'].round(0)
            
            st.dataframe(
                df_top_sobre,
                width='stretch',
                column_config={
                    "EXCESO_INVENTARIO": st.column_config.NumberColumn(
                        "Exceso",
                        format="%.0f",
                        help="Unidades por encima del inventario objetivo"
                    ),
                    "COBERTURA_MESES": st.column_config.NumberColumn(
                        "Cobertura (meses)",
                        format="%.2f",
                        help="Meses de inventario disponible al ritmo actual"
                    ),
                    "PROM_12M": st.column_config.NumberColumn(
                        "Prom. Mensual",
                        format="%.0f"
                    )
                }
            )
            
            st.info("💡 **Recomendación**: Productos con sobrestock pueden generar costos de almacenamiento innecesarios. Considera no reordenar hasta que el inventario baje al nivel objetivo.")
            
        else:
            st.success("✅ No hay productos con sobrestock. Todos los niveles de inventario están dentro del objetivo o por debajo.")
        
        st.markdown("---")
        
    # TAB 2: Análisis Resumido
    with tab2:
        st.header("Análisis Resumido")
        
        # Filtros
        st.subheader("🔍 Filtros")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            filtro_abc = st.multiselect(
                "Clasificación ABC",
                options=['A', 'B', 'C'],
                default=['A', 'B', 'C']
            )
        
        with col2:
            filtro_xyz = st.multiselect(
                "Clasificación XYZ",
                options=['X', 'Y', 'Z'],
                default=['X', 'Y', 'Z']
            )
        
        with col3:
            filtro_estado = st.multiselect(
                "Estado",
                options=['FALTA INV.', 'OK'],
                default=['FALTA INV.', 'OK']
            )
        
        with col4:
            filtro_demanda = st.multiselect(
                "Nivel de Demanda",
                options=['SIN MOV.', 'BAJA', 'MEDIA', 'ALTA'],
                default=['BAJA', 'MEDIA', 'ALTA']
            )
        
        with col5:
            # Nuevo filtro de sobrestock
            filtro_sobrestock = st.selectbox(
                "Estado de Stock",
                options=['Todos', 'Solo Sobrestock', 'Solo Falta/Normal'],
                index=0
            )
        
        # Búsqueda por código
        buscar_codigo = st.text_input("🔎 Buscar por código de producto", "")
        # Aplicar filtros
        df_filtrado = df.copy()
        df_filtrado = df_filtrado[df_filtrado['ABC'].isin(filtro_abc)]
        df_filtrado = df_filtrado[df_filtrado['XYZ'].isin(filtro_xyz)]
        df_filtrado = df_filtrado[df_filtrado['ESTADO'].isin(filtro_estado)]
        df_filtrado = df_filtrado[df_filtrado['DEMANDA_NIVEL'].isin(filtro_demanda)]
        
        # Aplicar filtro de sobrestock
        if filtro_sobrestock == 'Solo Sobrestock':
            df_filtrado = df_filtrado[df_filtrado['SALDO_ACTUAL'] > df_filtrado['INV_OBJETIVO']]
        elif filtro_sobrestock == 'Solo Falta/Normal':
            df_filtrado = df_filtrado[df_filtrado['SALDO_ACTUAL'] <= df_filtrado['INV_OBJETIVO']]
        
        if buscar_codigo:
            df_filtrado = df_filtrado[
                df_filtrado['COD_PROD'].astype(str).str.contains(buscar_codigo, case=False, na=False) |
                df_filtrado['DESCRIPCION'].astype(str).str.contains(buscar_codigo, case=False, na=False)
            ]
        
        st.info(f"📋 Mostrando {len(df_filtrado):,} de {len(df):,} productos")
        
        # Resumen visual rápido de productos filtrados
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Filtrado", f"{len(df_filtrado):,}")
        with col2:
            st.metric("Compra Total", f"{df_filtrado['CANT_A_COMPRAR'].sum():,.0f}")
        with col3:
            valor_filtrado = df_filtrado['VALOR_VENTAS_12M'].sum()
            valor_filtrado_fmt = f"₡{valor_filtrado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            st.metric("Valor Filtrado", valor_filtrado_fmt)
        with col4:
            productos_criticos = len(df_filtrado[df_filtrado['ESTADO'] == 'FALTA INV.'])
            st.metric("Productos Críticos", f"{productos_criticos}")
        
        st.markdown("---")
        
        # Ordenamiento
        col1, col2 = st.columns([3, 1])
        with col1:
            ordenar_por = st.selectbox(
                "Ordenar por:",
                options=['CANT_A_COMPRAR', 'VALOR_VENTAS_12M', 'PROM_12M', 'CV', 'SALDO_ACTUAL'],
                index=0
            )
        with col2:
            orden_desc = st.checkbox("Descendente", value=True)
        
        df_filtrado = df_filtrado.sort_values(ordenar_por, ascending=not orden_desc)
        # Columnas específicas para la tabla resumida (ORDEN EXACTO)
        cols_resumido = [
            'COD_PROD',
            'DESCRIPCION', 
            'PROM_12M',
            'ABC',
            'XYZ',
            'ABC_XYZ',
            'DEMANDA_NIVEL',
            'INV_MIN',
            'INV_MAX',
            'SALDO_ACTUAL',
            'ESTADO',
            'CANT_A_COMPRAR'
        ]
        
        # Verificar que todas las columnas existan en el dataframe
        cols_resumido = [c for c in cols_resumido if c in df_filtrado.columns]
        
        # PAGINACIÓN: Mostrar tabla solo dentro de expander con paginación
        with st.expander("📊 Ver Tabla de Análisis Resumido", expanded=False):
            st.caption("💡 La tabla está oculta por defecto para mejorar el rendimiento. Haz clic para expandir.")
            
            # Configuración de paginación
            productos_por_pagina = st.select_slider(
                "Productos por página:",
                options=[25, 50, 100, 200, 500],
                value=50
            )
            
            total_productos = len(df_filtrado)
            total_paginas = max(1, (total_productos + productos_por_pagina - 1) // productos_por_pagina)
            
            col1, col2, col3 = st.columns([2, 3, 2])
            with col2:
                pagina_actual = st.number_input(
                    f"Página (de {total_paginas}):",
                    min_value=1,
                    max_value=total_paginas,
                    value=1,
                    step=1
                )
            
            # Calcular índices
            inicio = (pagina_actual - 1) * productos_por_pagina
            fin = min(inicio + productos_por_pagina, total_productos)
            
            df_pagina = df_filtrado.iloc[inicio:fin]
            
            st.caption(f"Mostrando productos {inicio + 1} a {fin} de {total_productos}")
            
            # Función para colorear filas
            def color_estado(row):
                if row['ESTADO'] == 'FALTA INV.':
                    return ['background-color: #ffebee'] * len(row)
                elif 'ABC_XYZ' in row.index and row['ABC_XYZ'] in ['AX', 'AY']:
                    return ['background-color: #e8f5e9'] * len(row)
                return [''] * len(row)
            
            # Mostrar tabla paginada con columnas específicas
            df_styled = df_pagina[cols_resumido].style.apply(color_estado, axis=1)
            st.dataframe(
                df_styled,
                width='stretch',
                height=600,
                column_config={
                    "COD_PROD": st.column_config.TextColumn("Código", width="medium"),
                    "DESCRIPCION": st.column_config.TextColumn("Descripción", width="large"),
                    "PROM_12M": st.column_config.NumberColumn("Prom. Mensual", format="%.2f", help="Promedio de ventas mensuales últimos 12 meses"),
                    "ABC": st.column_config.TextColumn("ABC", width="small"),
                    "XYZ": st.column_config.TextColumn("XYZ", width="small"),
                    "ABC_XYZ": st.column_config.TextColumn("ABC-XYZ", width="small"),
                    "DEMANDA_NIVEL": st.column_config.TextColumn("Demanda", width="small"),
                    "INV_MIN": st.column_config.NumberColumn("Inv. Mín", format="%.2f", help="Inventario mínimo (demanda durante lead time)"),
                    "INV_MAX": st.column_config.NumberColumn("Inv. Máx", format="%.2f", help="Inventario máximo"),
                    "SALDO_ACTUAL": st.column_config.NumberColumn("Saldo Actual", format="%.2f", help="Inventario actual en stock"),
                    "ESTADO": st.column_config.TextColumn("Estado", width="small", help="Estado del inventario"),
                    "CANT_A_COMPRAR": st.column_config.NumberColumn("A Comprar", format="%.2f", help="Cantidad sugerida de compra")
                }
            )
            # Navegación rápida
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("◀️ Primera página", disabled=(pagina_actual == 1)):
                    st.rerun()
            with col2:
                st.write(f"Página {pagina_actual} / {total_paginas}")
            with col3:
                if st.button("Última página ▶️", disabled=(pagina_actual == total_paginas)):
                    st.rerun()
        
        # Alternativa: Mostrar solo Top 20 productos críticos siempre visible
        st.markdown("---")
        st.subheader("🔥 Top 20 Productos Prioritarios")
        
        # Determinar productos prioritarios (con mayor CANT_A_COMPRAR o críticos)
        df_prioritarios = df_filtrado[
            (df_filtrado['CANT_A_COMPRAR'] > 0) | (df_filtrado['ESTADO'] == 'FALTA INV.')
        ].nlargest(20, 'CANT_A_COMPRAR')
        
        if len(df_prioritarios) > 0:
            # Asegurar que usamos las mismas columnas que la tabla principal
            st.dataframe(
                df_prioritarios[cols_resumido],
                width='stretch',
                height=400,
                column_config={
                    "COD_PROD": st.column_config.TextColumn("Código", width="medium"),
                    "DESCRIPCION": st.column_config.TextColumn("Descripción", width="large"),
                    "PROM_12M": st.column_config.NumberColumn("Prom. Mensual", format="%.2f", help="Promedio de ventas mensuales últimos 12 meses"),
                    "ABC": st.column_config.TextColumn("ABC", width="small"),
                    "XYZ": st.column_config.TextColumn("XYZ", width="small"),
                    "ABC_XYZ": st.column_config.TextColumn("ABC-XYZ", width="small"),
                    "DEMANDA_NIVEL": st.column_config.TextColumn("Demanda", width="small"),
                    "INV_MIN": st.column_config.NumberColumn("Inv. Mín", format="%.2f", help="Inventario mínimo (demanda durante lead time)"),
                    "INV_MAX": st.column_config.NumberColumn("Inv. Máx", format="%.2f", help="Inventario máximo"),
                    "SALDO_ACTUAL": st.column_config.NumberColumn("Saldo Actual", format="%.2f", help="Inventario actual en stock"),
                    "ESTADO": st.column_config.TextColumn("Estado", width="small", help="Estado del inventario"),
                    "CANT_A_COMPRAR": st.column_config.NumberColumn("A Comprar", format="%.2f", help="Cantidad sugerida de compra")
                }
            )
        else:
            st.info("✅ No hay productos prioritarios que requieran atención inmediata.")
        
        st.markdown("---")
        
    # TAB 3: Gráficos y Tendencias
    with tab3:
        st.header("Análisis Gráfico y Tendencias")
        
        # Análisis de ventas por mes
        if meses_cols:
            st.subheader("📈 Tendencia de Ventas Mensuales")
            
            # Agregar ventas totales por mes
            ventas_por_mes = df[meses_cols].sum()
            fig_tendencia = go.Figure()
            fig_tendencia.add_trace(go.Scatter(
                x=ventas_por_mes.index,
                y=ventas_por_mes.values,
                mode='lines+markers',
                name='Ventas Totales',
                line=dict(color='#636efa', width=3),
                marker=dict(size=8)
            ))
            fig_tendencia.update_layout(
                title="Evolución de Ventas Totales - Últimos 12 Meses",
                xaxis_title="Mes",
                yaxis_title="Unidades Vendidas",
                hovermode='x unified',
                height=400
            )
            st.plotly_chart(fig_tendencia, width='stretch')
        
        # Distribución de compras sugeridas
        st.subheader("💰 Distribución de Compras Sugeridas")
        df_comprar = df[df['CANT_A_COMPRAR'] > 0]
        
        col1, col2 = st.columns(2)
        
        with col1:
            fig_compras_abc = px.bar(
                df_comprar.groupby('ABC')['CANT_A_COMPRAR'].sum().reset_index(),
                x='ABC',
                y='CANT_A_COMPRAR',
                title="Compras Sugeridas por Clasificación ABC",
                color='ABC',
                color_discrete_map={'A': '#00cc96', 'B': '#ffa15a', 'C': '#ef553b'},
                text='CANT_A_COMPRAR'
            )
            fig_compras_abc.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            st.plotly_chart(fig_compras_abc, width='stretch')
        
        with col2:
            fig_compras_demanda = px.bar(
                df_comprar.groupby('DEMANDA_NIVEL')['CANT_A_COMPRAR'].sum().reset_index(),
                x='DEMANDA_NIVEL',
                y='CANT_A_COMPRAR',
                title="Compras por Nivel de Demanda",
                color='DEMANDA_NIVEL',
                text='CANT_A_COMPRAR'
            )
            fig_compras_demanda.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            st.plotly_chart(fig_compras_demanda, width='stretch')
            # Scatter: CV vs Ventas
        st.subheader("🎯 Análisis de Variabilidad vs Volumen")
        fig_scatter = px.scatter(
            df,
            x='PROM_12M',
            y='CV',
            size='VALOR_VENTAS_12M',
            color='ABC_XYZ',
            hover_data=['COD_PROD', 'DESCRIPCION', 'CANT_A_COMPRAR'],
            title="Variabilidad vs Promedio de Ventas (tamaño = valor ventas)",
            labels={
                'PROM_12M': 'Promedio Mensual', 
                'CV': 'Coeficiente de Variación'
            }
        )
        fig_scatter.update_layout(height=500)
        st.plotly_chart(fig_scatter, width='stretch')

        # Nueva sección: Análisis de Estado de Inventario
        st.subheader("📊 Estado General del Inventario")
        
        # Calcular categorías de estado
        df['ESTADO_INVENTARIO'] = 'Normal'
        df.loc[df['SALDO_ACTUAL'] < df['INV_MIN'], 'ESTADO_INVENTARIO'] = 'Crítico (< Min)'
        df.loc[(df['SALDO_ACTUAL'] >= df['INV_MIN']) & (df['SALDO_ACTUAL'] < df['INV_OBJETIVO']), 'ESTADO_INVENTARIO'] = 'Bajo Objetivo'
        df.loc[df['SALDO_ACTUAL'] > df['INV_OBJETIVO'] * 1.5, 'ESTADO_INVENTARIO'] = 'Sobrestock Alto (>150%)'
        df.loc[(df['SALDO_ACTUAL'] > df['INV_OBJETIVO']) & (df['SALDO_ACTUAL'] <= df['INV_OBJETIVO'] * 1.5), 'ESTADO_INVENTARIO'] = 'Sobrestock Moderado'
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Distribución por estado de inventario
            estado_counts = df['ESTADO_INVENTARIO'].value_counts()
            fig_estado = px.pie(
                values=estado_counts.values,
                names=estado_counts.index,
                title="Distribución por Estado de Inventario",
                color=estado_counts.index,
                color_discrete_map={
                    'Crítico (< Min)': '#d32f2f',
                    'Bajo Objetivo': '#ffa726',
                    'Normal': '#66bb6a',
                    'Sobrestock Moderado': '#42a5f5',
                    'Sobrestock Alto (>150%)': '#7e57c2'
                }
            )
            fig_estado.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_estado, width='stretch')
        
        with col2:
            # Gráfico de barras: Productos críticos vs Sobrestock por ABC
            df_estado_abc = df.groupby(['ABC', 'ESTADO_INVENTARIO']).size().reset_index(name='Cantidad')
            fig_abc_estado = px.bar(
                df_estado_abc,
                x='ABC',
                y='Cantidad',
                color='ESTADO_INVENTARIO',
                title="Estado de Inventario por Clasificación ABC",
                barmode='stack',
                color_discrete_map={
                    'Crítico (< Min)': '#d32f2f',
                    'Bajo Objetivo': '#ffa726',
                    'Normal': '#66bb6a',
                    'Sobrestock Moderado': '#42a5f5',
                    'Sobrestock Alto (>150%)': '#7e57c2'
                }
            )
            st.plotly_chart(fig_abc_estado, width='stretch')
            # Análisis de Cobertura vs Objetivo
        st.subheader("📈 Análisis de Cobertura Real vs Objetivo")
        
        # Calcular cobertura real y diferencia
        df['COBERTURA_REAL'] = df['SALDO_ACTUAL'] / df['PROM_12M'].replace(0, np.nan)
        df['COBERTURA_OBJETIVO'] = df['INV_OBJETIVO'] / df['PROM_12M'].replace(0, np.nan)
        df['DIFERENCIA_COBERTURA'] = df['COBERTURA_REAL'] - df['COBERTURA_OBJETIVO']
        
        # Filtrar valores extremos para mejor visualización
        df_cob_viz = df[df['COBERTURA_REAL'] <= 5].copy()  # Máximo 5 meses para visualización
        
        fig_cobertura_scatter = px.scatter(
            df_cob_viz,
            x='COBERTURA_OBJETIVO',
            y='COBERTURA_REAL',
            color='ABC',
            size='VALOR_VENTAS_12M',
            hover_data=['COD_PROD', 'DESCRIPCION', 'DIFERENCIA_COBERTURA'],
            title="Cobertura Real vs Objetivo (tamaño = valor ventas)",
            labels={
                'COBERTURA_OBJETIVO': 'Cobertura Objetivo (meses)',
                'COBERTURA_REAL': 'Cobertura Real (meses)'
            },
            color_discrete_map={'A': '#00cc96', 'B': '#ffa15a', 'C': '#ef553b'}
        )
        
        # Agregar línea diagonal (cobertura ideal = objetivo)
        max_cob = max(df_cob_viz['COBERTURA_OBJETIVO'].max(), df_cob_viz['COBERTURA_REAL'].max())
        fig_cobertura_scatter.add_trace(
            go.Scatter(
                x=[0, max_cob],
                y=[0, max_cob],
                mode='lines',
                name='Línea Ideal',
                line=dict(color='gray', dash='dash'),
                showlegend=True
            )
        )
        fig_cobertura_scatter.update_layout(height=500)
        st.plotly_chart(fig_cobertura_scatter, width='stretch')
        
        st.info("💡 **Lectura del gráfico**: Productos **por encima** de la línea gris tienen sobrestock. Productos **por debajo** necesitan reabastecimiento.")
        
    # TAB 4: Análisis por Cliente
    with tab4:
        st.header("👥 Análisis por Cliente")
        
        if st.session_state.analisis_clientes is None:
            st.warning("⚠️ El análisis por cliente no está disponible.")
            st.info("""
            Para habilitar esta funcionalidad, asegúrate de que tu archivo de ventas incluya las siguientes columnas:
            - **NOM_CLIENTE**: Nombre del cliente
            - **DES_PROVEEDOR**: Descripción del proveedor
            
            Vuelve a cargar el archivo con estas columnas para acceder al análisis por cliente.
            """)
        else:
            df_clientes = st.session_state.analisis_clientes["resumen_clientes"]
            ventas_detalle = st.session_state.analisis_clientes["ventas_detalle"]
            
            # SECCIÓN 1: Dashboard de Clientes
            st.subheader("📊 Dashboard de Clientes")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_clientes = len(df_clientes)
                st.metric("Total Clientes", f"{total_clientes:,}")
            
            with col2:
                clientes_a = len(df_clientes[df_clientes["ABC_CLIENTE"] == "A"])
                pct_a = (clientes_a / total_clientes * 100) if total_clientes > 0 else 0
                st.metric("Clientes A (80%)", f"{clientes_a}", f"{pct_a:.1f}%")
            
            with col3:
                valor_total = df_clientes["VALOR_TOTAL_12M"].sum()
                valor_formateado = f"₡{valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                st.metric("Valor Total 12M", valor_formateado)
            
            st.markdown("---")
            # Gráfico de Pareto
            st.subheader("📈 Análisis de Pareto - Top Clientes")
            
            df_top = df_clientes.head(20).copy()
            
            fig_pareto = go.Figure()
            
            # Barras de valor
            fig_pareto.add_trace(go.Bar(
                x=df_top["NOM_CLIENTE"],
                y=df_top["VALOR_TOTAL_12M"],
                name="Valor Ventas",
                marker_color='#636efa',
                yaxis='y',
                text=df_top["VALOR_TOTAL_12M"],
                texttemplate='₡%{text:,.0f}',
                textposition='outside'
            ))
            
            # Línea de participación acumulada
            fig_pareto.add_trace(go.Scatter(
                x=df_top["NOM_CLIENTE"],
                y=df_top["PARTICIPACION_ACUM"] * 100,
                name="% Acumulado",
                marker_color='#ef553b',
                yaxis='y2',
                mode='lines+markers',
                line=dict(width=3)
            ))
            
            fig_pareto.update_layout(
                title="Top 20 Clientes - Análisis 80/20",
                xaxis=dict(title="Cliente", tickangle=-45),
                yaxis=dict(title="Valor Ventas (₡)", side='left'),
                yaxis2=dict(title="% Acumulado", side='right', overlaying='y', range=[0, 100]),
                hovermode='x unified',
                height=500,
                showlegend=True
            )
            
            # Línea de referencia 80%
            fig_pareto.add_hline(y=80, line_dash="dash", line_color="red", 
                     annotation_text="80%")
            
            st.plotly_chart(fig_pareto, width='stretch')
            
            # Distribución ABC
            col1, col2 = st.columns(2)
            
            with col1:
                abc_counts = df_clientes["ABC_CLIENTE"].value_counts()
                fig_abc_cli = px.pie(
                    values=abc_counts.values,
                    names=abc_counts.index,
                    title="Distribución ABC de Clientes",
                    color=abc_counts.index,
                    color_discrete_map={'A': '#00cc96', 'B': '#ffa15a', 'C': '#ef553b'},
                    hole=0.4
                )
                fig_abc_cli.update_traces(textposition='inside', textinfo='percent+label+value')
                st.plotly_chart(fig_abc_cli, width='stretch')
            
            with col2:
                # Métricas promedio por clasificación
                st.markdown("#### Métricas Promedio por Clasificación")
                for abc in ['A', 'B', 'C']:
                    df_abc = df_clientes[df_clientes["ABC_CLIENTE"] == abc]
                    if len(df_abc) > 0:
                        prom_valor = df_abc["VALOR_TOTAL_12M"].mean()
                        prom_productos = df_abc["PRODUCTOS_DISTINTOS"].mean()
                        st.markdown(f"""
                        **Clientes {abc}:**
                        - Valor prom: ₡{prom_valor:,.0f}
                        - Productos prom: {prom_productos:.1f}
                        """)
                        st.markdown("---")
                
                # SECCIÓN 2: Tabla de Clientes con Selección
                st.subheader("📋 Selecciona un Cliente para Análisis Detallado")
                st.caption("Haz clic en una fila para ver el análisis completo del cliente")
            
                # Preparar tabla para mostrar
                df_clientes_display = df_clientes.copy()
                df_clientes_display["VALOR_TOTAL_12M_FMT"] = df_clientes_display["VALOR_TOTAL_12M"].apply(
                    lambda x: f"₡{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
                df_clientes_display["PARTICIPACION_FMT"] = (df_clientes_display["PARTICIPACION"] * 100).round(2).astype(str) + "%"
            
                cols_display = [
                    "RANKING",
                    "NOM_CLIENTE",
                    "VALOR_TOTAL_12M_FMT",
                    "PARTICIPACION_FMT",
                    "ABC_CLIENTE",
                    "PRODUCTOS_DISTINTOS",
                    "MESES_ACTIVOS",
                    "DIAS_DESDE_ULTIMA_COMPRA"
                ]
            
                event = st.dataframe(
                    df_clientes_display[cols_display],
                    on_select="rerun",
                    selection_mode="single-row",
                    width='stretch',
                    height=400,
                    column_config={
                        "RANKING": st.column_config.NumberColumn("#", width="small"),
                        "NOM_CLIENTE": st.column_config.TextColumn("Cliente", width="large"),
                        "VALOR_TOTAL_12M_FMT": st.column_config.TextColumn("Valor 12M", width="medium"),
                        "PARTICIPACION_FMT": st.column_config.TextColumn("% Part.", width="small"),
                        "ABC_CLIENTE": st.column_config.TextColumn("ABC", width="small"),
                        "PRODUCTOS_DISTINTOS": st.column_config.NumberColumn("Productos", width="small"),
                        "MESES_ACTIVOS": st.column_config.NumberColumn("Meses", width="small"),
                        "DIAS_DESDE_ULTIMA_COMPRA": st.column_config.NumberColumn("Días últ. compra", width="small")
                    }
                )
                # SECCIÓN 3: Análisis del Cliente Seleccionado
                if event.selection.rows:
                    cliente_idx = event.selection.rows[0]
                    cliente_data = df_clientes.iloc[cliente_idx]
                    cliente_nombre = cliente_data["NOM_CLIENTE"]
                
                    st.markdown("---")
                    st.header(f"📊 Análisis Detallado: {cliente_nombre}")
                    
                    # Badge de clasificación
                    abc_color = {"A": "🟢", "B": "🟡", "C": "🔴"}
                    st.markdown(f"### {abc_color.get(cliente_data['ABC_CLIENTE'], '⚪')} Cliente Clasificación: **{cliente_data['ABC_CLIENTE']}**")
                    
                    # Métricas del cliente
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        valor_fmt = f"₡{cliente_data['VALOR_TOTAL_12M']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        st.metric("Ventas 12M", valor_fmt)
                    
                    with col2:
                        st.metric("Productos", f"{int(cliente_data['PRODUCTOS_DISTINTOS'])}")
                    
                    with col3:
                        ticket_fmt = f"₡{cliente_data['TICKET_PROMEDIO']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        st.metric("Ticket Promedio", ticket_fmt)
                    
                    with col4:
                        st.metric("Última Compra", f"{int(cliente_data['DIAS_DESDE_ULTIMA_COMPRA'])} días")
                    
                    st.markdown("---")
                    
                    # Analizar productos del cliente
                    productos_cliente = analizar_productos_cliente(
                        cliente_nombre,
                        ventas_detalle,
                        st.session_state.df_inventario_original,
                        st.session_state.df_resultado
                    )
                    
                    if len(productos_cliente) == 0:
                        st.warning("No se encontraron productos para este cliente.")
                    else:
                        # SECCIÓN 4: Alertas Automáticas
                        alertas = identificar_alertas_cliente(productos_cliente)
                        
                        if alertas["count_criticos"] > 0 or alertas["count_riesgo"] > 0:
                            st.subheader("🚨 Alertas de Riesgo")
                            
                            if alertas["count_criticos"] > 0:
                                st.error(f"""
                                ⚠️ **ALERTA DE ALTO RIESGO**: {alertas['count_criticos']} productos que este cliente compra frecuentemente están con **FALTA DE INVENTARIO**.
                                
                                **Riesgo**: Pérdida de cliente clave por desabastecimiento.
                                """)
                                
                                with st.expander("Ver productos críticos"):
                                    df_criticos = pd.DataFrame(alertas["productos_criticos"])
                                    st.dataframe(
                                        df_criticos[["COD_PROD", "Inventario.DESCRIPCION", "MESES_CON_COMPRA", "CANTIDAD_12M", "ESTADO"]],
                                        width='stretch'
                                    )
                            
                            if alertas["count_riesgo"] > 0:
                                st.warning(f"""
                                ⚠️ **Productos en Riesgo**: {alertas['count_riesgo']} productos tienen inventario bajo considerando las compras de este cliente.
                                """)
                        
                        st.markdown("---")
                        # Top productos del cliente
                        st.subheader("🏆 Top Productos del Cliente")
                        
                        # Tabs para diferentes vistas
                        tab_tabla, tab_graficos = st.tabs(["📋 Tabla Detallada", "📊 Gráficos"])
                        
                        with tab_tabla:
                            # Formatear valores para display
                            df_productos_display = productos_cliente.head(50).copy()
                            
                            if "VALOR_12M" in df_productos_display.columns:
                                df_productos_display["VALOR_12M_FMT"] = df_productos_display["VALOR_12M"].apply(
                                    lambda x: f"₡{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                                )
                            
                            if "PARTICIPACION_CLIENTE" in df_productos_display.columns:
                                df_productos_display["PARTICIPACION_CLIENTE_FMT"] = (df_productos_display["PARTICIPACION_CLIENTE"] * 100).round(2).astype(str) + "%"                        
                            
                            # Columnas a mostrar
                            cols_productos = [
                                "RANKING",
                                "COD_PROD",
                                "DESCRIPCION",
                                "DES_PROVEEDOR",
                                "CANTIDAD_12M",
                                "VALOR_12M_FMT",
                                "PARTICIPACION_CLIENTE_FMT",
                                "MESES_CON_COMPRA"
                            ]
                            
                            # Agregar columnas del análisis general si existen
                            if "ABC_XYZ" in df_productos_display.columns:
                                cols_productos.append("ABC_XYZ")
                            if "SALDO_ACTUAL" in df_productos_display.columns:
                                cols_productos.append("SALDO_ACTUAL")
                            if "ESTADO" in df_productos_display.columns:
                                cols_productos.append("ESTADO")
                            if "CANT_A_COMPRAR" in df_productos_display.columns:
                                cols_productos.append("CANT_A_COMPRAR")
                            
                            cols_disponibles = [c for c in cols_productos if c in df_productos_display.columns]
                            
                            st.dataframe(
                                df_productos_display[cols_disponibles],
                                width='stretch',
                                height=500,
                                column_config={
                                    "RANKING": st.column_config.NumberColumn("#", width="small"),
                                    "COD_PROD": st.column_config.TextColumn("Código", width="medium"),
                                    "DESCRIPCION": st.column_config.TextColumn("Descripción", width="large"),
                                    "DES_PROVEEDOR": st.column_config.TextColumn("Proveedor", width="medium"),
                                    "CANTIDAD_12M": st.column_config.NumberColumn("Cant. 12M", format="%.0f"),
                                    "VALOR_12M_FMT": st.column_config.TextColumn("Valor 12M"),
                                    "PARTICIPACION_CLIENTE_FMT": st.column_config.TextColumn("% Cliente"),
                                    "MESES_CON_COMPRA": st.column_config.NumberColumn("Meses", width="small"),
                                    "ABC_XYZ": st.column_config.TextColumn("ABC-XYZ", width="small"),
                                    "SALDO_ACTUAL": st.column_config.NumberColumn("Inventario", format="%.0f"),
                                    "ESTADO": st.column_config.TextColumn("Estado", width="small"),
                                    "CANT_A_COMPRAR": st.column_config.NumberColumn("A Comprar", format="%.0f")
                                }
                            )
                            
                            # Botón para descargar productos del cliente
                            csv_cliente = productos_cliente.to_csv(index=False).encode('utf-8-sig')
                            st.download_button(
                                label=f"⬇️ Descargar productos de {cliente_nombre}",
                                data=csv_cliente,
                                file_name=f"productos_{cliente_nombre.replace(' ', '_')}.csv",
                                mime="text/csv"
                            )
                            with tab_graficos:
                                col1, col2 = st.columns(2)
                    
                            with col1:
                                # Top 10 productos por valor
                                df_top10 = productos_cliente.head(10)
                                fig_top10 = px.bar(
                                    df_top10,
                                    x="VALOR_12M",
                                    y="COD_PROD",
                                    orientation='h',
                                    title=f"Top 10 Productos por Valor",
                                    labels={"VALOR_12M": "Valor 12M (₡)", "COD_PROD": "Producto"},
                                    text="VALOR_12M"
                                )
                                fig_top10.update_traces(texttemplate='₡%{text:,.0f}', textposition='outside')
                                fig_top10.update_layout(height=400, yaxis={'categoryorder':'total ascending'})
                                st.plotly_chart(fig_top10, width='stretch')
                            
                            with col2:
                                # Distribución por proveedor
                                proveedores_agg = productos_cliente.groupby("DES_PROVEEDOR")["VALOR_12M"].sum().reset_index()
                                proveedores_agg = proveedores_agg.sort_values("VALOR_12M", ascending=False).head(10)
                                
                                fig_prov = px.pie(
                                    proveedores_agg,
                                    values="VALOR_12M",
                                    names="DES_PROVEEDOR",
                                    title="Distribución por Proveedor (Top 10)",
                                    hole=0.4
                                )
                                fig_prov.update_traces(textposition='inside', textinfo='percent+label')
                                st.plotly_chart(fig_prov, width='stretch')
                            
                            # Evolución mensual
                            st.subheader("📈 Evolución de Compras Mensuales")
                            evolucion = calcular_evolucion_cliente(cliente_nombre, ventas_detalle)
                            
                            if len(evolucion) > 0:
                                fig_evol = go.Figure()
                                
                                fig_evol.add_trace(go.Scatter(
                                    x=evolucion["Mes"],
                                    y=evolucion["Valor"],
                                    mode='lines+markers',
                                    name='Valor',
                                    line=dict(color='#636efa', width=3),
                                    marker=dict(size=8),
                                    yaxis='y'
                                ))
                                
                                fig_evol.add_trace(go.Scatter(
                                    x=evolucion["Mes"],
                                    y=evolucion["Cantidad"],
                                    mode='lines+markers',
                                    name='Cantidad',
                                    line=dict(color='#00cc96', width=3),
                                    marker=dict(size=8),
                                    yaxis='y2'
                                ))
                                
                                fig_evol.update_layout(
                                    title=f"Evolución de Compras - {cliente_nombre}",
                                    xaxis=dict(title="Mes"),
                                    yaxis=dict(title="Valor (₡)", side='left'),
                                    yaxis2=dict(title="Cantidad", side='right', overlaying='y'),
                                    hovermode='x unified',
                                    height=400,
                                    showlegend=True
                                )
                                
                                st.plotly_chart(fig_evol, width='stretch')
                                st.markdown("---")
                    
                        # SECCIÓN DE OPORTUNIDADES
                        st.subheader("💡 Oportunidades y Recomendaciones")
                        
                        st.info("""
                        **Funcionalidad en desarrollo:**
                        - Productos complementarios recomendados
                        - Productos equivalentes/similares sugeridos
                        
                        Un experto podrá configurar estas relaciones para mejorar las recomendaciones.
                        """)
                    
                        # Placeholder para futuras funcionalidades
                        with st.expander("Productos Relacionados (Próximamente)"):
                            st.markdown("""
                            Esta sección permitirá:
                            - Asociar productos equivalentes (ej: mismo producto de diferente marca)
                            - Definir productos complementarios (ej: cables con conectores)
                            - El sistema sugerirá automáticamente estos productos al analizar clientes
                            """)
                else:
                    st.info("👆 Selecciona un cliente de la tabla para ver su análisis detallado")

# TAB 5: Exportar Datos
    with tab5:
        st.header("💾 Exportar Resultados")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔥 Descargar Excel completo")
            st.download_button(
                label="⬇️ Descargar resultado_analisis_compras.xlsx",
                data=st.session_state.excel_bytes,
                file_name="resultado_analisis_compras.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.caption("Incluye todas las columnas y formato original")
        
        with col2:
            st.subheader("📄 Descargar CSV filtrado")
            csv_filtrado = df_filtrado.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="⬇️ Descargar datos filtrados (CSV)",
                data=csv_filtrado,
                file_name="analisis_filtrado.csv",
                mime="text/csv",
                use_container_width=True
            )
            st.caption("Descarga solo los datos con filtros aplicados")
        
        st.markdown("---")
        
        # Opción de guardar localmente
        st.subheader("💻 Guardar en disco local")
        default_downloads = Path.home() / "Downloads"
        
        col1, col2 = st.columns([3, 2])
        with col1:
            carpeta_destino = st.text_input("Carpeta de destino", value=str(default_downloads))
        with col2:
            nombre_archivo = st.text_input("Nombre del archivo", value="resultado_analisis_compras.xlsx")
        
        if st.button("💾 Guardar en PC", use_container_width=True):
            try:
                carpeta = Path(carpeta_destino).expanduser()
                carpeta.mkdir(parents=True, exist_ok=True)
                destino = carpeta / nombre_archivo
                with open(destino, "wb") as f:
                    f.write(st.session_state.excel_bytes.getbuffer())
                st.success(f"✅ Archivo guardado exitosamente en: {destino}")
            except Exception as e:
                st.error(f"❌ No se pudo guardar el archivo: {e}")
else:
    # Pantalla inicial
    st.info("👈 Configura los parámetros y carga los archivos en el panel lateral para comenzar el análisis")
    
    # Instrucciones
    with st.expander("📖 Guía de uso", expanded=True):
        st.markdown("""
        ### Cómo usar esta herramienta:
        
        1. **Carga los archivos** en el panel lateral:
           - **Ventas**: Debe contener `COD_PROD`, `Fecha`, `Cantidad`, `PRECIO_DESCUENTO`
           - **Ventas (Opcional)**: `NOM_CLIENTE`, `DES_PROVEEDOR` para habilitar análisis por cliente
           - **Inventario**: Debe contener `COD_PROD`, `Inventario.DESCRIPCION`, `SALDO ACTUAL`
        
        2. **Ajusta los parámetros** según tu negocio:
           - Lead Time: días que tarda el reabastecimiento
           - Cobertura: meses de inventario que deseas mantener
           - Días de venta: cuántos días a la semana vendes
        
        3. **Ejecuta el análisis** y explora:
           - Dashboard con métricas clave
           - Tabla interactiva con filtros avanzados
           - Gráficos de tendencias y distribución
           - Análisis por cliente (si tienes las columnas)
           - Exportación de resultados
        
        ### Clasificaciones:
        
        **ABC (Por valor de ventas):**
        - **A**: Productos que representan el 80% del valor (alta prioridad)
        - **B**: Productos entre 80-95% del valor
        - **C**: Productos que representan el último 5% del valor
        
        **XYZ (Por variabilidad):**
        - **X**: Demanda estable (CV ≤ 0.30)
        - **Y**: Demanda moderadamente variable (0.30 < CV ≤ 0.60)
        - **Z**: Demanda errática (CV > 0.60)
        
        **Nota importante**: Los productos sin ventas en los últimos 12 meses se excluyen automáticamente del análisis.
        """)
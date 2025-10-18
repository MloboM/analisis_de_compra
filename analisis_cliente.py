import pandas as pd
import numpy as np
import unidecode

def validar_columnas_cliente(df_ventas, configuracion=None):
    """
    Valida si el archivo de ventas tiene las columnas necesarias para análisis por cliente.
    Retorna: (tiene_columnas, columnas_faltantes)
    """
    # Si no se proporciona configuración, usar valores predeterminados
    if configuracion is None:
        columnas_requeridas = {"NOM_CLIENTE", "DES_PROVEEDOR"}
    else:
        columnas_requeridas = {
            configuracion['VENTAS']['NOM_CLIENTE'], 
            configuracion['VENTAS']['DES_PROVEEDOR']
        }
    
    columnas_presentes = set(df_ventas.columns)
    
    tiene_columnas = columnas_requeridas.issubset(columnas_presentes)
    columnas_faltantes = columnas_requeridas - columnas_presentes
    
    return tiene_columnas, list(columnas_faltantes)

def clasificar_abc_clientes(df_clientes: pd.DataFrame, col_valor: str = "VALOR_TOTAL_12M") -> pd.DataFrame:
    """
    Clasifica clientes según ABC (por valor de ventas).
    
    Categorías:
    - A: hasta 80% de participación
    - B: hasta 95% de participación
    - C: resto
    """
    df = df_clientes.copy()
    total = df[col_valor].sum()
    
    # Ordenar por valor descendente
    df = df.sort_values(col_valor, ascending=False).reset_index(drop=True)
    df["PARTICIPACION"] = df[col_valor] / total if total > 0 else 0
    df["PARTICIPACION_ACUM"] = df["PARTICIPACION"].cumsum()
    
    def clasificar(p):
        if p <= 0.80:
            return "A"
        elif p <= 0.95:
            return "B"
        else:
            return "C"
    
    df["ABC_CLIENTE"] = df["PARTICIPACION_ACUM"].apply(clasificar)
    
    return df

def analizar_clientes(ventas_df: pd.DataFrame, inventario_df: pd.DataFrame, configuracion=None) -> dict:
    """
    Genera análisis completo por cliente con soporte para nombres de columnas configurables.
    """
    # Configuración predeterminada si no se proporciona
    if configuracion is None:
        configuracion = {
            'VENTAS': {
                'NOM_CLIENTE': 'NOM_CLIENTE',
                'COD_PROD': 'COD_PROD',
                'CANTIDAD': 'Cantidad',
                'PRECIO_DESCUENTO': 'PRECIO_DESCUENTO',
                'FECHA': 'Fecha'
            }
        }

    # Usar nombres configurados
    nom_cliente = configuracion['VENTAS']['NOM_CLIENTE']
    cod_prod = configuracion['VENTAS']['COD_PROD']
    cantidad = configuracion['VENTAS']['CANTIDAD']
    precio = configuracion['VENTAS']['PRECIO_DESCUENTO']
    fecha = configuracion['VENTAS']['FECHA']

    # Normalizar nombres de clientes
    ventas_df[nom_cliente] = ventas_df[nom_cliente].apply(lambda x: unidecode.unidecode(str(x)) if pd.notna(x) else x)

    # Preparar datos de ventas
    ventas = ventas_df.copy()
    ventas[cantidad] = pd.to_numeric(ventas[cantidad], errors="coerce").fillna(0)
    ventas[precio] = pd.to_numeric(ventas[precio], errors="coerce").fillna(0)
    ventas[fecha] = pd.to_datetime(ventas[fecha], dayfirst=True, errors="coerce")
    ventas["Mes"] = ventas[fecha].dt.to_period("M").dt.to_timestamp()
    ventas["Ingreso"] = ventas[cantidad] * ventas[precio]
    
    # Últimos 12 meses
    ref = pd.Timestamp.today().to_period("M").to_timestamp()
    fecha_inicio = ref - pd.DateOffset(months=12)
    ventas_12m = ventas[ventas[fecha] >= fecha_inicio].copy()
    
    # Agregación por cliente
    clientes_agg = ventas_12m.groupby(nom_cliente).agg({
        "Ingreso": "sum",
        cantidad: "sum",
        cod_prod: "nunique",
        fecha: ["min", "max"],
        "Mes": "nunique"
    }).reset_index()
    
    # Aplanar columnas multi-nivel
    clientes_agg.columns = [
        nom_cliente,
        "VALOR_TOTAL_12M",
        "CANTIDAD_TOTAL_12M", 
        "PRODUCTOS_DISTINTOS",
        "PRIMERA_COMPRA",
        "ULTIMA_COMPRA",
        "MESES_ACTIVOS"
    ]
    
    # Calcular métricas adicionales
    clientes_agg["TICKET_PROMEDIO"] = clientes_agg["VALOR_TOTAL_12M"] / clientes_agg["MESES_ACTIVOS"]
    clientes_agg["DIAS_DESDE_ULTIMA_COMPRA"] = (pd.Timestamp.today() - clientes_agg["ULTIMA_COMPRA"]).dt.days
    
    # Clasificación ABC
    clientes_agg = clasificar_abc_clientes(clientes_agg)
    
    # Ranking
    clientes_agg["RANKING"] = range(1, len(clientes_agg) + 1)
    
    # Reordenar columnas
    cols_orden = [
        "RANKING",
        "NOM_CLIENTE",
        "VALOR_TOTAL_12M",
        "CANTIDAD_TOTAL_12M",
        "PARTICIPACION",
        "PARTICIPACION_ACUM",
        "ABC_CLIENTE",
        "PRODUCTOS_DISTINTOS",
        "MESES_ACTIVOS",
        "TICKET_PROMEDIO",
        "DIAS_DESDE_ULTIMA_COMPRA",
        "PRIMERA_COMPRA",
        "ULTIMA_COMPRA"
    ]
    
    clientes_agg = clientes_agg[cols_orden]
    
    return {
        "resumen_clientes": clientes_agg,
        "ventas_detalle": ventas_12m
    }

def analizar_productos_cliente(cliente: str, ventas_df: pd.DataFrame, 
                               inventario_df: pd.DataFrame,
                               analisis_general: pd.DataFrame,
                               configuracion=None) -> pd.DataFrame:
    """
    Analiza los productos que compra un cliente específico con soporte para nombres de columnas configurables.
    """
    # Configuración predeterminada si no se proporciona
    if configuracion is None:
        configuracion = {
            'VENTAS': {
                'NOM_CLIENTE': 'NOM_CLIENTE',
                'COD_PROD': 'COD_PROD',
                'CANTIDAD': 'Cantidad',
                'DES_PROVEEDOR': 'DES_PROVEEDOR',
                'FECHA': 'Fecha'
            },
            'INVENTARIO': {
                'COD_PROD': 'COD_PROD',
                'DESCRIPCION': 'Inventario.DESCRIPCION',
                'SALDO_ACTUAL': 'SALDO ACTUAL'
            }
        }

    # Usar nombres configurados
    nom_cliente = configuracion['VENTAS']['NOM_CLIENTE']
    cod_prod = configuracion['VENTAS']['COD_PROD']
    cantidad = configuracion['VENTAS']['CANTIDAD']
    des_proveedor = configuracion['VENTAS']['DES_PROVEEDOR']
    inv_cod_prod = configuracion['INVENTARIO']['COD_PROD']
    inv_descripcion = configuracion['INVENTARIO']['DESCRIPCION']
    inv_saldo = configuracion['INVENTARIO']['SALDO_ACTUAL']

    # Normalizar nombres de productos y proveedores
    ventas_df[cod_prod] = ventas_df[cod_prod].apply(lambda x: unidecode.unidecode(str(x)) if pd.notna(x) else x)
    ventas_df[des_proveedor] = ventas_df[des_proveedor].apply(lambda x: unidecode.unidecode(str(x)) if pd.notna(x) else x)

    # Filtrar ventas del cliente
    ventas_cliente = ventas_df[ventas_df[nom_cliente] == cliente].copy()
    
    if len(ventas_cliente) == 0:
        return pd.DataFrame()
    
    # Agregación por producto
    productos_agg = ventas_cliente.groupby([cod_prod, des_proveedor]).agg({
        cantidad: "sum",
        "Ingreso": "sum",
        "Mes": "nunique"
    }).reset_index()
    
    productos_agg.columns = [
        "COD_PROD",
        "DES_PROVEEDOR",
        "CANTIDAD_12M",
        "VALOR_12M",
        "MESES_CON_COMPRA"
    ]
    
    # Merge con inventario para obtener descripción y saldo
    productos_agg = productos_agg.merge(
        inventario_df[[inv_cod_prod, inv_descripcion, inv_saldo]],
        left_on="COD_PROD",
        right_on=inv_cod_prod,
        how="left"
    )

    # Merge con análisis general para obtener estado y cantidad a comprar
    if analisis_general is not None and len(analisis_general) > 0:
        cols_analisis = ["COD_PROD", "ABC", "XYZ", "ABC_XYZ", "ESTADO", "CANT_A_COMPRAR", 
                        "INV_MIN", "INV_OBJETIVO", "PROM_12M"]
        cols_disponibles = [c for c in cols_analisis if c in analisis_general.columns]
        
        productos_agg = productos_agg.merge(
            analisis_general[cols_disponibles],
            on="COD_PROD",
            how="left"
        )
    
    # Reordenar columnas
    cols_orden = [
        "RANKING",
        "COD_PROD",
        "DESCRIPCION",
        "DES_PROVEEDOR",
        "CANTIDAD_12M",
        "VALOR_12M",
        "PARTICIPACION_CLIENTE",
        "MESES_CON_COMPRA"
    ]
    
    # Agregar columnas del análisis general si existen
    if "ABC" in productos_agg.columns:
        cols_orden.extend(["ABC", "XYZ", "ABC_XYZ"])
    if "SALDO_ACTUAL" in productos_agg.columns:
        cols_orden.append("SALDO_ACTUAL")
    if "ESTADO" in productos_agg.columns:
        cols_orden.extend(["ESTADO", "INV_MIN", "INV_OBJETIVO", "CANT_A_COMPRAR"])
    if "PROM_12M" in productos_agg.columns:
        cols_orden.append("PROM_12M")
    
    # Filtrar solo columnas que existen
    cols_orden = [c for c in cols_orden if c in productos_agg.columns]
    productos_agg = productos_agg[cols_orden]
    
    return productos_agg

def identificar_alertas_cliente(productos_cliente: pd.DataFrame) -> dict:
    """
    Identifica alertas de riesgo para un cliente específico.
    
    Returns:
        dict con:
        - criticos: productos que compra frecuentemente y están con falta
        - riesgo: productos con inventario bajo
        - count: contadores
    """
    
    alertas = {
        "productos_criticos": [],
        "productos_riesgo": [],
        "count_criticos": 0,
        "count_riesgo": 0
    }
    
    if len(productos_cliente) == 0:
        return alertas
    
    # Productos críticos: compra frecuente + falta inventario
    if "ESTADO" in productos_cliente.columns and "MESES_CON_COMPRA" in productos_cliente.columns:
        criticos = productos_cliente[
            (productos_cliente["ESTADO"] == "FALTA INV.") &
            (productos_cliente["MESES_CON_COMPRA"] >= 6)  # Compra al menos 6 meses
        ].copy()
        
        if len(criticos) > 0:
            alertas["productos_criticos"] = criticos.to_dict("records")
            alertas["count_criticos"] = len(criticos)
    
    # Productos en riesgo: inventario < promedio mensual de compra del cliente
    if all(col in productos_cliente.columns for col in ["SALDO_ACTUAL", "CANTIDAD_12M"]):
        productos_cliente["PROM_MENSUAL_CLIENTE"] = productos_cliente["CANTIDAD_12M"] / 12
        
        riesgo = productos_cliente[
            (productos_cliente["SALDO_ACTUAL"] < productos_cliente["PROM_MENSUAL_CLIENTE"] * 2) &
            (productos_cliente["MESES_CON_COMPRA"] >= 6)
        ].copy()
        
        if len(riesgo) > 0:
            alertas["productos_riesgo"] = riesgo.to_dict("records")
            alertas["count_riesgo"] = len(riesgo)
    
    return alertas

def calcular_evolucion_cliente(cliente: str, ventas_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula la evolución mensual de compras de un cliente.
    
    Returns:
        DataFrame con columnas: Mes, Valor, Cantidad
    """
    ventas_cliente = ventas_df[ventas_df["NOM_CLIENTE"] == cliente].copy()
    
    if len(ventas_cliente) == 0:
        return pd.DataFrame()
    
    evolucion = ventas_cliente.groupby("Mes").agg({
        "Ingreso": "sum",
        "Cantidad": "sum"
    }).reset_index()
    
    evolucion.columns = ["Mes", "Valor", "Cantidad"]
    evolucion = evolucion.sort_values("Mes")
    
    return evolucion
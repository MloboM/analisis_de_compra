# analisis_core.py
import pandas as pd
import numpy as np
from io import BytesIO

# ====== Parámetros por defecto (pueden venir de la UI) ======
DEFAULTS = {
    "LEAD_TIME_DIAS": 4,
    "COBERTURA_MESES": 1,
    "VENTA_DIAS_SEMANA": 6,
    "Z": 1.65,  # ~95% servicio
    "ABC_UMBRAL_A": 0.80,
    "ABC_UMBRAL_B": 0.95,
    "XYZ_UMBRAL_X": 0.10,
    "XYZ_UMBRAL_Y": 0.25,
}

def es_fecha_col(col: str) -> bool:
    col_l = str(col).strip().lower()
    meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic",
             "jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
    if "-" in col_l:
        m, _ = col_l.split("-", 1)
        if m in meses:
            return True
    return False

def preparar_ventas_df(df: pd.DataFrame) -> pd.DataFrame:
    """Acepta DF transaccional (COD_PROD, Fecha, Cantidad) o pivoteado por mes (sep-24...) y devuelve: COD_PROD, Mes, Cantidad."""
    # Caso A: transaccional
    if {"COD_PROD","Fecha","Cantidad"}.issubset(df.columns):
        out = df.copy()
        out["Cantidad"] = pd.to_numeric(out["Cantidad"], errors="coerce")
        out["Fecha"] = pd.to_datetime(out["Fecha"], dayfirst=True, errors="coerce")
        if out["Fecha"].isna().all():
            raise ValueError("No se pudo interpretar 'Fecha' en ventas.")
        out["Mes"] = out["Fecha"].dt.to_period("M").dt.to_timestamp()
        return out.groupby(["COD_PROD","Mes"], as_index=False)["Cantidad"].sum()

    # Caso B: pivoteada por mes
    mes_cols = [c for c in df.columns if es_fecha_col(c)]
    if not mes_cols:
        raise ValueError("Ventas no parecen transaccionales ni pivoteadas por mes.")
    melted = df.melt(id_vars=["COD_PROD"], value_vars=mes_cols, var_name="MesTxt", value_name="Cantidad")
    melted["Cantidad"] = pd.to_numeric(melted["Cantidad"], errors="coerce").fillna(0)

    def parse_mes(mtxt: str) -> pd.Timestamp:
        mapa = {"ene":"jan","abr":"apr","ago":"aug","dic":"dec"}
        pref = mtxt.split("-")[0][:3].lower()
        yy = mtxt.split("-")[1]
        pref_eng = mapa.get(pref, pref)
        yy_full = "20" + yy if len(yy)==2 else yy
        return pd.to_datetime(f"01-{pref_eng}-{yy_full}", format="%d-%b-%Y")

    melted["Mes"] = melted["MesTxt"].apply(parse_mes)
    return melted.groupby(["COD_PROD","Mes"], as_index=False)["Cantidad"].sum()

def preparar_inventario_df(inv: pd.DataFrame) -> pd.DataFrame:
    rename = {"Inventario.DESCRIPCION":"DESCRIPCION",
              "COSTO PROMEDIO":"COSTO_PROMEDIO",
              "SALDO ACTUAL":"SALDO_ACTUAL"}
    inv2 = inv.rename(columns=rename).copy()
    for c in ["COSTO_PROMEDIO","SALDO_ACTUAL"]:
        inv2[c] = pd.to_numeric(inv2[c], errors="coerce").fillna(0)
    expected = ["COD_PROD","DESCRIPCION","COSTO_PROMEDIO","SALDO_ACTUAL"]
    missing = [c for c in expected if c not in inv2.columns]
    if missing:
        raise ValueError(f"Inventario con columnas faltantes: {missing}. Esperado: {expected}")
    return inv2[expected]

def clasificar_abc(df_valor: pd.DataFrame, A=0.80, B=0.95) -> pd.DataFrame:
    total = df_valor["ValorConsumo"].sum()
    df_valor = df_valor.sort_values("ValorConsumo", ascending=False).reset_index(drop=True)
    df_valor["Participacion"] = (df_valor["ValorConsumo"]/total) if total>0 else 0
    df_valor["ParticipacionAcum"] = df_valor["Participacion"].cumsum()
    def etiqueta(p):
        if p <= A: return "A"
        elif p <= B: return "B"
        else: return "C"
    df_valor["ABC"] = df_valor["ParticipacionAcum"].apply(etiqueta)
    return df_valor

def etiqueta_es(ts: pd.Timestamp) -> str:
    mapa = {"Jan":"ene","Feb":"feb","Mar":"mar","Apr":"abr","May":"may","Jun":"jun",
            "Jul":"jul","Aug":"ago","Sep":"sep","Oct":"oct","Nov":"nov","Dec":"dic"}
    eng = ts.strftime("%b").title()
    yy = ts.strftime("%y")
    return f"{mapa.get(eng,eng.lower())}-{yy}"

def clasificar_xyz_por_cv(cv, X=0.10, Y=0.25):
    if cv <= X: return "X"
    elif cv <= Y: return "Y"
    else: return "Z"

def analizar(ventas_df: pd.DataFrame,
             inventario_df: pd.DataFrame,
             LEAD_TIME_DIAS=DEFAULTS["LEAD_TIME_DIAS"],
             COBERTURA_MESES=DEFAULTS["COBERTURA_MESES"],
             VENTA_DIAS_SEMANA=DEFAULTS["VENTA_DIAS_SEMANA"],
             Z=DEFAULTS["Z"],
             ABC_UMBRAL_A=DEFAULTS["ABC_UMBRAL_A"],
             ABC_UMBRAL_B=DEFAULTS["ABC_UMBRAL_B"],
             XYZ_UMBRAL_X=DEFAULTS["XYZ_UMBRAL_X"],
             XYZ_UMBRAL_Y=DEFAULTS["XYZ_UMBRAL_Y"]
             ) -> BytesIO:
    """Devuelve un Excel (BytesIO) con una hoja: Analisis."""
    DIAS_VENTA_X_MES = int(VENTA_DIAS_SEMANA * 4.33)

    ventas = preparar_ventas_df(ventas_df)
    inv = preparar_inventario_df(inventario_df)

    pivot = ventas.pivot_table(index="COD_PROD", columns="Mes", values="Cantidad", aggfunc="sum").fillna(0)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)

    # Ventana fija: últimos 12 meses, incluye mes en curso
    ref = pd.Timestamp.today().to_period("M").to_timestamp()
    last12 = pd.date_range(end=ref, periods=12, freq="MS")
    for c in last12:
        if c not in pivot.columns:
            pivot[c] = 0
    ventas_last12 = pivot[last12].copy()

    # Métricas
    prom12 = ventas_last12.mean(axis=1)
    desv = pivot.std(axis=1, ddof=1).fillna(0)
    cv = (desv / pivot.mean(axis=1).replace(0, np.nan)).fillna(0)

    total_cant = pivot.sum(axis=1)
    costos = inv.set_index("COD_PROD")["COSTO_PROMEDIO"]
    valor = (total_cant * costos).fillna(0)
    df_valor = clasificar_abc(pd.DataFrame({"COD_PROD": valor.index, "ValorConsumo": valor.values}),
                              A=ABC_UMBRAL_A, B=ABC_UMBRAL_B)

    prom_diaria = prom12 / max(DIAS_VENTA_X_MES, 1)
    demanda_lt = prom_diaria * LEAD_TIME_DIAS
    desv_diaria = desv / np.sqrt(max(len(pivot.columns), 1)) / (DIAS_VENTA_X_MES ** 0.5)
    ss = Z * desv_diaria * (LEAD_TIME_DIAS ** 0.5)

    inv_min = (demanda_lt + ss).fillna(0)
    inv_obj = inv_min + (prom12 * COBERTURA_MESES)
    inv_max = inv_obj

    resumen = (inv
               .merge(prom12.rename("PROM_12M"), left_on="COD_PROD", right_index=True)
               .merge(desv.rename("DesviacionEstandar"), left_on="COD_PROD", right_index=True)
               .merge(cv.rename("CV"), left_on="COD_PROD", right_index=True)
               .merge(df_valor[["COD_PROD","ValorConsumo","Participacion","ParticipacionAcum","ABC"]], on="COD_PROD"))

    resumen["XYZ"] = resumen["CV"].apply(lambda x: clasificar_xyz_por_cv(x, XYZ_UMBRAL_X, XYZ_UMBRAL_Y))
    resumen["ABC_XYZ"] = resumen["ABC"] + resumen["XYZ"]

    # Frecuencia de meses con venta
    meses_con_venta = (ventas_last12 > 0).sum(axis=1)
    def demanda_freq(n):
        if n <= 0: return "SIN MOV."
        elif n <= 3: return "BAJA"
        elif n <= 6: return "MEDIA"
        else: return "ALTA"
    resumen = resumen.merge(meses_con_venta.rename("MESES_CON_VENTA_12M"),
                            left_on="COD_PROD", right_index=True)
    resumen["DEMANDA_NIVEL"] = resumen["MESES_CON_VENTA_12M"].apply(demanda_freq)

    # INV_MIN/MAX/OBJ
    resumen = (resumen
               .merge(inv_min.rename("INV_MIN"), left_on="COD_PROD", right_index=True)
               .merge(inv_max.rename("INV_MAX"), left_on="COD_PROD", right_index=True)
               .merge(inv_obj.rename("INV_OBJETIVO"), left_on="COD_PROD", right_index=True))

    # Agregar 12 meses como columnas etiquetadas
    colnames_last12 = [etiqueta_es(c) for c in ventas_last12.columns]
    ventas_last12.columns = colnames_last12
    resumen = resumen.merge(ventas_last12, left_on="COD_PROD", right_index=True)

    # Totales y valores
    resumen["CANT_A_COMPRAR"] = (resumen["INV_OBJETIVO"] - resumen["SALDO_ACTUAL"]).clip(lower=0).round(2)
    resumen["ESTADO"] = np.where(resumen["SALDO_ACTUAL"] < resumen["INV_MIN"], "FALTA INV.", "OK")
    resumen["TOTAL_VENTAS_12M"] = resumen[colnames_last12].sum(axis=1)
    resumen["VALOR_VENTAS_12M"] = resumen["TOTAL_VENTAS_12M"] * resumen["COSTO_PROMEDIO"]

    # Redondeos numéricos a 2 decimales
    for col in ["PROM_12M","DesviacionEstandar","INV_MIN","INV_MAX","INV_OBJETIVO",
                "CANT_A_COMPRAR","VALOR_VENTAS_12M","ValorConsumo","COSTO_PROMEDIO"]:
        if col in resumen.columns:
            resumen[col] = pd.to_numeric(resumen[col], errors="coerce").round(2)

    # CV / Participación en fracción (0..1), redondeadas (para formato % en Excel)
    resumen["CV"] = pd.to_numeric(resumen["CV"], errors="coerce").round(4)
    resumen["Participacion"] = pd.to_numeric(resumen["Participacion"], errors="coerce").round(4)
    resumen["ParticipacionAcum"] = pd.to_numeric(resumen["ParticipacionAcum"], errors="coerce").round(4)

    # Orden de columnas
    base = ["COD_PROD","DESCRIPCION","COSTO_PROMEDIO","SALDO_ACTUAL"]
    analit = ["TOTAL_VENTAS_12M","PROM_12M","VALOR_VENTAS_12M",
              "DesviacionEstandar","CV","ValorConsumo",
              "Participacion","ParticipacionAcum","ABC","XYZ","ABC_XYZ",
              "MESES_CON_VENTA_12M","DEMANDA_NIVEL",
              "INV_MIN","INV_MAX","INV_OBJETIVO","ESTADO","CANT_A_COMPRAR"]
    cols = base + colnames_last12 + analit
    cols = [c for c in cols if c in resumen.columns]

    # Generar Excel en memoria
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as w:
        resumen[cols].to_excel(w, index=False, sheet_name="Analisis")
        wb = w.book
        ws = w.sheets["Analisis"]
        formato_porcentaje = wb.add_format({'num_format': '0.00%'})
        formato_numero     = wb.add_format({'num_format': '0.00'})

        # Aplicar formato % a CV/Participaciones
        col_idx = {name: i for i, name in enumerate(resumen[cols].columns)}
        for name in ["CV","Participacion","ParticipacionAcum"]:
            if name in col_idx:
                ws.set_column(col_idx[name], col_idx[name], 12, formato_porcentaje)
        # DesvEstd en unidades
        if "DesviacionEstandar" in col_idx:
            ws.set_column(col_idx["DesviacionEstandar"], col_idx["DesviacionEstandar"], 12, formato_numero)
    output.seek(0)
    return output

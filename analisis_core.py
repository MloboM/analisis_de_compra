import pandas as pd
import numpy as np
from io import BytesIO

# ====== Parámetros por defecto ======
DEFAULTS = {
    "LEAD_TIME_DIAS": 4,
    "COBERTURA_MESES": 1,
    "VENTA_DIAS_SEMANA": 6,
    "XYZ_UMBRAL_X": 0.30,  # X: Estables
    "XYZ_UMBRAL_Y": 0.60,  # Y: Moderadamente variables, >0.60 = Z
}

def preparar_ventas_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ventas transaccionales: COD_PROD, Fecha, Cantidad, PRECIO_DESCUENTO."""
    expected = {"COD_PROD", "Fecha", "Cantidad", "PRECIO_DESCUENTO"}
    if not expected.issubset(df.columns):
        raise ValueError(f"Ventas deben tener columnas {expected}")

    out = df.copy()
    out["Cantidad"] = pd.to_numeric(out["Cantidad"], errors="coerce").fillna(0)
    out["PRECIO_DESCUENTO"] = pd.to_numeric(out["PRECIO_DESCUENTO"], errors="coerce").fillna(0)
    out["Fecha"] = pd.to_datetime(out["Fecha"], dayfirst=True, errors="coerce")
    if out["Fecha"].isna().all():
        raise ValueError("No se pudo interpretar 'Fecha' en ventas.")

    out["Mes"] = out["Fecha"].dt.to_period("M").dt.to_timestamp()
    out["Ingreso"] = out["Cantidad"] * out["PRECIO_DESCUENTO"]

    return out.groupby(["COD_PROD", "Mes"], as_index=False).agg(
        Cantidad=("Cantidad", "sum"),
        Ingreso=("Ingreso", "sum")
    )

def preparar_inventario_df(inv: pd.DataFrame) -> pd.DataFrame:
    """Inventario sin costo. Requiere: COD_PROD, Inventario.DESCRIPCION, SALDO ACTUAL."""
    rename = {"Inventario.DESCRIPCION": "DESCRIPCION",
              "SALDO ACTUAL": "SALDO_ACTUAL"}
    inv2 = inv.rename(columns=rename).copy()
    if "SALDO_ACTUAL" in inv2.columns:
        inv2["SALDO_ACTUAL"] = pd.to_numeric(inv2["SALDO_ACTUAL"], errors="coerce").fillna(0)

    expected = ["COD_PROD", "DESCRIPCION", "SALDO_ACTUAL"]
    missing = [c for c in expected if c not in inv2.columns]
    if missing:
        raise ValueError(f"Inventario con columnas faltantes: {missing}")
    return inv2[expected]

def clasificar_abc(df_valor: pd.DataFrame) -> pd.DataFrame:
    """ABC por ingresos: A hasta 80%, B hasta 95%, C restante."""
    total = df_valor["ValorConsumo"].sum()
    df_valor = df_valor.sort_values("ValorConsumo", ascending=False).reset_index(drop=True)
    df_valor["Participacion"] = (df_valor["ValorConsumo"]/total) if total > 0 else 0
    df_valor["ParticipacionAcum"] = df_valor["Participacion"].cumsum()
    def etiqueta(p):
        if p <= 0.80: return "A"
        elif p <= 0.95: return "B"
        else: return "C"
    df_valor["ABC"] = df_valor["ParticipacionAcum"].apply(etiqueta)
    return df_valor

def etiqueta_es(ts: pd.Timestamp) -> str:
    mapa = {"Jan":"ene","Feb":"feb","Mar":"mar","Apr":"abr","May":"may","Jun":"jun",
            "Jul":"jul","Aug":"ago","Sep":"sep","Oct":"oct","Nov":"nov","Dec":"dic"}
    eng = ts.strftime("%b").title()
    yy = ts.strftime("%y")
    return f"{mapa.get(eng,eng.lower())}-{yy}"

def clasificar_xyz_por_cv(cv, X=0.30, Y=0.60):
    if cv <= X: return "X"
    elif cv <= Y: return "Y"
    else: return "Z"

def analizar(ventas_df: pd.DataFrame,
             inventario_df: pd.DataFrame,
             LEAD_TIME_DIAS=DEFAULTS["LEAD_TIME_DIAS"],
             COBERTURA_MESES=DEFAULTS["COBERTURA_MESES"],
             VENTA_DIAS_SEMANA=DEFAULTS["VENTA_DIAS_SEMANA"],
             XYZ_UMBRAL_X=DEFAULTS["XYZ_UMBRAL_X"],
             XYZ_UMBRAL_Y=DEFAULTS["XYZ_UMBRAL_Y"]
             ) -> BytesIO:

    DIAS_VENTA_X_MES = int(VENTA_DIAS_SEMANA * 4.33)

    ventas = preparar_ventas_df(ventas_df)
    inv = preparar_inventario_df(inventario_df)

    pivot_qty = ventas.pivot_table(index="COD_PROD", columns="Mes", values="Cantidad", aggfunc="sum").fillna(0)
    pivot_ing = ventas.pivot_table(index="COD_PROD", columns="Mes", values="Ingreso", aggfunc="sum").fillna(0)

    ref = pd.Timestamp.today().to_period("M").to_timestamp()
    last12 = pd.date_range(end=ref, periods=12, freq="MS")
    for c in last12:
        if c not in pivot_qty.columns: pivot_qty[c] = 0
        if c not in pivot_ing.columns: pivot_ing[c] = 0

    ventas_last12 = pivot_qty[last12]
    ingresos_last12 = pivot_ing[last12]

    prom12 = ventas_last12.mean(axis=1)
    desv = pivot_qty.std(axis=1, ddof=1).fillna(0)
    cv = (desv / pivot_qty.mean(axis=1).replace(0, np.nan)).fillna(0)

    ingresos_12m = ingresos_last12.sum(axis=1)
    df_valor = clasificar_abc(pd.DataFrame({"COD_PROD": ingresos_12m.index,
                                            "ValorConsumo": ingresos_12m.values}))

    prom_diaria = prom12 / max(DIAS_VENTA_X_MES, 1)
    demanda_lt = prom_diaria * LEAD_TIME_DIAS

    inv_min = demanda_lt.fillna(0)
    inv_obj = inv_min + (prom12 * COBERTURA_MESES)
    inv_max = inv_obj

    resumen = (inv
               .merge(prom12.rename("PROM_12M"), left_on="COD_PROD", right_index=True)
               .merge(desv.rename("DesviacionEstandar"), left_on="COD_PROD", right_index=True)
               .merge(cv.rename("CV"), left_on="COD_PROD", right_index=True)
               .merge(df_valor[["COD_PROD","ValorConsumo","Participacion","ParticipacionAcum","ABC"]], on="COD_PROD"))

    resumen["XYZ"] = resumen["CV"].apply(lambda x: clasificar_xyz_por_cv(x, XYZ_UMBRAL_X, XYZ_UMBRAL_Y))
    resumen["ABC_XYZ"] = resumen["ABC"] + resumen["XYZ"]

    meses_con_venta = (ventas_last12 > 0).sum(axis=1)
    def demanda_freq(n):
        if n <= 0: return "SIN MOV."
        elif n <= 3: return "BAJA"
        elif n <= 6: return "MEDIA"
        else: return "ALTA"
    resumen = resumen.merge(meses_con_venta.rename("MESES_CON_VENTA_12M"),
                            left_on="COD_PROD", right_index=True)
    resumen["DEMANDA_NIVEL"] = resumen["MESES_CON_VENTA_12M"].apply(demanda_freq)

    resumen = (resumen
               .merge(inv_min.rename("INV_MIN"), left_on="COD_PROD", right_index=True)
               .merge(inv_max.rename("INV_MAX"), left_on="COD_PROD", right_index=True)
               .merge(inv_obj.rename("INV_OBJETIVO"), left_on="COD_PROD", right_index=True))

    colnames_last12 = [etiqueta_es(c) for c in ventas_last12.columns]
    ventas_last12.columns = colnames_last12
    resumen = resumen.merge(ventas_last12, left_on="COD_PROD", right_index=True)

    resumen["CANT_A_COMPRAR"] = (resumen["INV_OBJETIVO"] - resumen["SALDO_ACTUAL"]).clip(lower=0).round(2)
    resumen["ESTADO"] = np.where(resumen["SALDO_ACTUAL"] < resumen["INV_MIN"], "FALTA INV.", "OK")
    resumen["TOTAL_VENTAS_12M"] = resumen[colnames_last12].sum(axis=1)

    # VALOR_VENTAS_12M = Ingresos 12M
    resumen = resumen.merge(ingresos_12m.rename("VALOR_VENTAS_12M"),
                            left_on="COD_PROD", right_index=True, how="left")
    resumen["VALOR_VENTAS_12M"] = resumen["VALOR_VENTAS_12M"].fillna(0)

    # Redondeos
    for col in ["PROM_12M","DesviacionEstandar","INV_MIN","INV_MAX","INV_OBJETIVO",
                "CANT_A_COMPRAR","VALOR_VENTAS_12M","ValorConsumo"]:
        if col in resumen.columns:
            resumen[col] = pd.to_numeric(resumen[col], errors="coerce").round(2)
    resumen["CV"] = pd.to_numeric(resumen["CV"], errors="coerce").round(4)
    resumen["Participacion"] = pd.to_numeric(resumen["Participacion"], errors="coerce").round(4)
    resumen["ParticipacionAcum"] = pd.to_numeric(resumen["ParticipicionAcum"] if "ParticipicionAcum" in resumen.columns else resumen["ParticipacionAcum"], errors="coerce").round(4)

    base = ["COD_PROD","DESCRIPCION","SALDO_ACTUAL"]
    analit = ["TOTAL_VENTAS_12M","PROM_12M","VALOR_VENTAS_12M",
              "DesviacionEstandar","CV","ValorConsumo",
              "Participacion","ParticipacionAcum","ABC","XYZ","ABC_XYZ",
              "MESES_CON_VENTA_12M","DEMANDA_NIVEL",
              "INV_MIN","INV_MAX","INV_OBJETIVO","ESTADO","CANT_A_COMPRAR"]
    cols = base + colnames_last12 + analit
    cols = [c for c in cols if c in resumen.columns]

    # ===== Excel en memoria (con defensas contra RangeIndex) =====
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as w:
        # 1) Forzar encabezados string
        to_write = resumen[cols].copy()
        to_write.columns = [str(c) for c in to_write.columns]

        to_write.to_excel(w, index=False, sheet_name="Analisis")
        wb = w.book
        ws = w.sheets["Analisis"]

        try:
            formato_porcentaje = wb.add_format({'num_format': '0.00%'})
            formato_numero     = wb.add_format({'num_format': '0.00'})

            headers = list(to_write.columns)
            def pos(col_name: str):
                try:
                    return int(headers.index(col_name))
                except ValueError:
                    return None

            for name in ["CV","Participacion","ParticipacionAcum"]:
                cpos = pos(name)
                if cpos is not None:
                    ws.set_column(int(cpos), int(cpos), 12, formato_porcentaje)

            dpos = pos("DesviacionEstandar")
            if dpos is not None:
                ws.set_column(int(dpos), int(dpos), 12, formato_numero)

        except Exception:
            # Si algo raro ocurre (ej. tipos no soportados), seguimos sin formateo.
            pass

    output.seek(0)
    return output



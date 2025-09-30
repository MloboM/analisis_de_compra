import pandas as pd
import numpy as np
from pathlib import Path
import sys

# ===========================
# PARÁMETROS (ajusta a gusto)
# ===========================
LEAD_TIME_DIAS = 4
COBERTURA_MESES = 1
VENTA_DIAS_SEMANA = 6
DIAS_VENTA_X_MES = int(VENTA_DIAS_SEMANA * 4.33)  # ~26 si vendes de lunes a sábado
Z = 1.65  # Nivel de servicio 95%
ABC_UMBRAL_A = 0.80
ABC_UMBRAL_B = 0.95
XYZ_UMBRAL_X = 0.10
XYZ_UMBRAL_Y = 0.25

# ===========================
# ARCHIVOS
# ===========================
RUTA_VENTAS = "ventas.csv"
RUTA_INVENTARIO = "inventario.csv"
RUTA_SALIDA_EXCEL = "resultado_analisis_compras.xlsx"


def es_fecha_col(col: str) -> bool:
    col_l = col.strip().lower()
    meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic",
             "jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
    if "-" in col_l:
        m, _ = col_l.split("-", 1)
        if m in meses:
            return True
    return False


def preparar_ventas(path_csv: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path_csv, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path_csv, sep=";", encoding="utf-8-sig")

    # Caso A: transaccional
    if {"COD_PROD", "Fecha", "Cantidad"}.issubset(df.columns):
        df["Cantidad"] = pd.to_numeric(df["Cantidad"], errors="coerce")
        df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce")
        if df["Fecha"].isna().all():
            raise ValueError("No se pudo interpretar 'Fecha'")
        df["Mes"] = df["Fecha"].dt.to_period("M").dt.to_timestamp()
        return df.groupby(["COD_PROD","Mes"], as_index=False)["Cantidad"].sum()

    # Caso B: pivoteada por mes
    mes_cols = [c for c in df.columns if es_fecha_col(c)]
    if not mes_cols:
        raise ValueError("El archivo de ventas no es válido")
    melted = df.melt(id_vars=["COD_PROD"], value_vars=mes_cols,
                     var_name="MesTxt", value_name="Cantidad")
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


def preparar_inventario(path_csv: str) -> pd.DataFrame:
    try:
        inv = pd.read_csv(path_csv, encoding="utf-8-sig")
    except Exception:
        inv = pd.read_csv(path_csv, sep=";", encoding="utf-8-sig")
    rename = {"Inventario.DESCRIPCION":"DESCRIPCION",
              "COSTO PROMEDIO":"COSTO_PROMEDIO",
              "SALDO ACTUAL":"SALDO_ACTUAL"}
    inv = inv.rename(columns=rename)
    inv["COSTO_PROMEDIO"] = pd.to_numeric(inv["COSTO_PROMEDIO"], errors="coerce").fillna(0)
    inv["SALDO_ACTUAL"] = pd.to_numeric(inv["SALDO_ACTUAL"], errors="coerce").fillna(0)
    return inv[["COD_PROD","DESCRIPCION","COSTO_PROMEDIO","SALDO_ACTUAL"]]


def clasificar_abc(df_valor: pd.DataFrame) -> pd.DataFrame:
    total = df_valor["ValorConsumo"].sum()
    df_valor = df_valor.sort_values("ValorConsumo", ascending=False).reset_index(drop=True)
    df_valor["Participacion"] = df_valor["ValorConsumo"]/total if total>0 else 0
    df_valor["ParticipacionAcum"] = df_valor["Participacion"].cumsum()
    def etiqueta(p):
        if p <= ABC_UMBRAL_A: return "A"
        elif p <= ABC_UMBRAL_B: return "B"
        else: return "C"
    df_valor["ABC"] = df_valor["ParticipacionAcum"].apply(etiqueta)
    return df_valor


def clasificar_xyz(cv: float) -> str:
    if cv <= XYZ_UMBRAL_X: return "X"
    elif cv <= XYZ_UMBRAL_Y: return "Y"
    else: return "Z"


def etiqueta_es(ts: pd.Timestamp) -> str:
    mapa = {"Jan":"ene","Feb":"feb","Mar":"mar","Apr":"abr","May":"may","Jun":"jun",
            "Jul":"jul","Aug":"ago","Sep":"sep","Oct":"oct","Nov":"nov","Dec":"dic"}
    eng = ts.strftime("%b").title()
    yy = ts.strftime("%y")
    return f"{mapa.get(eng,eng.lower())}-{yy}"


def main():
    try:
        ventas = preparar_ventas(RUTA_VENTAS)
        inv = preparar_inventario(RUTA_INVENTARIO)

        pivot = ventas.pivot_table(index="COD_PROD", columns="Mes", values="Cantidad", aggfunc="sum").fillna(0)
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)

        # últimos 12 meses incluyendo mes en curso
        ref = pd.Timestamp.today().to_period("M").to_timestamp()
        last12 = pd.date_range(end=ref, periods=12, freq="MS")
        for c in last12:
            if c not in pivot.columns: pivot[c]=0
        ventas_last12 = pivot[last12]

        prom12 = ventas_last12.mean(axis=1)
        desv = pivot.std(axis=1, ddof=1).fillna(0)
        cv = (desv / pivot.mean(axis=1).replace(0,np.nan)).fillna(0)

        total_cant = pivot.sum(axis=1)
        costos = inv.set_index("COD_PROD")["COSTO_PROMEDIO"]
        valor = (total_cant * costos).fillna(0)
        df_valor = clasificar_abc(pd.DataFrame({"COD_PROD":valor.index,"ValorConsumo":valor.values}))

        prom_diaria = prom12 / max(DIAS_VENTA_X_MES,1)
        demanda_lt = prom_diaria * LEAD_TIME_DIAS
        desv_diaria = desv / np.sqrt(max(len(pivot.columns),1)) / (DIAS_VENTA_X_MES**0.5)
        ss = Z*desv_diaria*(LEAD_TIME_DIAS**0.5)

        inv_min = (demanda_lt+ss).fillna(0)
        inv_obj = inv_min + (prom12*COBERTURA_MESES)
        inv_max = inv_obj

        resumen = (inv
                   .merge(prom12.rename("PROM_12M"), left_on="COD_PROD", right_index=True)
                   .merge(desv.rename("DesviacionEstandar"), left_on="COD_PROD", right_index=True)
                   .merge(cv.rename("CV"), left_on="COD_PROD", right_index=True)
                   .merge(df_valor[["COD_PROD","ValorConsumo","Participacion","ParticipacionAcum","ABC"]],
                          on="COD_PROD"))

        resumen["XYZ"] = resumen["CV"].apply(clasificar_xyz)
        resumen["ABC_XYZ"] = resumen["ABC"]+resumen["XYZ"]

        # meses con movimiento
        meses_con_venta = (ventas_last12>0).sum(axis=1)
        def demanda_freq(n):
            if n<=0: return "SIN MOV."
            elif n<=3: return "BAJA"
            elif n<=6: return "MEDIA"
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

        resumen["CANT_A_COMPRAR"] = (resumen["INV_OBJETIVO"]-resumen["SALDO_ACTUAL"]).clip(lower=0).round(2)
        resumen["ESTADO"] = np.where(resumen["SALDO_ACTUAL"]<resumen["INV_MIN"],"FALTA INV.","OK")

        # ==== Nueva columna: total de ventas en los últimos 12 meses ====
        resumen["TOTAL_VENTAS_12M"] = resumen[colnames_last12].sum(axis=1)

        # ==== Nueva columna: valor de esas ventas multiplicado por el costo unitario ====
        resumen["VALOR_VENTAS_12M"] = resumen["TOTAL_VENTAS_12M"] * resumen["COSTO_PROMEDIO"]

        # ---------- FORMATEOS y REDONDEOS (según tu pedido) ----------
        # Redondeos numéricos a 2 decimales
        for col in ["PROM_12M","DesviacionEstandar","INV_MIN","INV_MAX","INV_OBJETIVO",
                    "CANT_A_COMPRAR","VALOR_VENTAS_12M","ValorConsumo","COSTO_PROMEDIO"]:
            if col in resumen.columns:
                resumen[col] = pd.to_numeric(resumen[col], errors="coerce").round(2)

        # CV / Participacion / ParticipacionAcum como fracción (0–1), redondeadas a 4 decimales
        # para que en Excel (0.00%) se vean con 2 decimales
        if "CV" in resumen.columns:
            resumen["CV"] = pd.to_numeric(resumen["CV"], errors="coerce").round(4)
        if "Participacion" in resumen.columns:
            resumen["Participacion"] = pd.to_numeric(resumen["Participacion"], errors="coerce").round(4)
        if "ParticipacionAcum" in resumen.columns:
            resumen["ParticipacionAcum"] = pd.to_numeric(resumen["ParticipicionAcum"] if "ParticipicionAcum" in resumen.columns else resumen["ParticipacionAcum"], errors="coerce").round(4)

        # --------------------------------------------------------------

        with pd.ExcelWriter(RUTA_SALIDA_EXCEL, engine="xlsxwriter") as w:
            base = ["COD_PROD","DESCRIPCION","COSTO_PROMEDIO","SALDO_ACTUAL"]
            analit = ["TOTAL_VENTAS_12M","PROM_12M","VALOR_VENTAS_12M",
                      "DesviacionEstandar","CV","ValorConsumo",
                      "Participacion","ParticipacionAcum","ABC","XYZ","ABC_XYZ",
                      "MESES_CON_VENTA_12M","DEMANDA_NIVEL",
                      "INV_MIN","INV_MAX","INV_OBJETIVO","ESTADO","CANT_A_COMPRAR"]
            cols = base+colnames_last12+analit

            # Escribimos datos
            resumen[cols].to_excel(w, index=False, sheet_name="Analisis")

            # Aplicamos formato en Excel
            workbook  = w.book
            ws = w.sheets["Analisis"]

            formato_porcentaje = workbook.add_format({'num_format': '0.00%'})
            formato_numero     = workbook.add_format({'num_format': '0.00'})

            # Mapa de nombre de columna -> índice
            col_idx = {name: i for i, name in enumerate(cols)}

            # Formato porcentaje para: CV, Participacion, ParticipacionAcum
            for name in ["CV","Participacion","ParticipacionAcum"]:
                if name in col_idx:
                    ws.set_column(col_idx[name], col_idx[name], 12, formato_porcentaje)

            # Formato numérico para DesviacionEstandar (2 decimales en unidades)
            if "DesviacionEstandar" in col_idx:
                ws.set_column(col_idx["DesviacionEstandar"], col_idx["DesviacionEstandar"], 12, formato_numero)

        print(f"OK: se generó {Path(RUTA_SALIDA_EXCEL).resolve()}")

    except Exception as e:
        print("[ERROR]",e)
        sys.exit(1)


if __name__=="__main__":
    main()


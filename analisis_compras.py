import pandas as pd
import numpy as np
from pathlib import Path
import sys

# ===========================
# PARÁMETROS (ajusta a gusto)
# ===========================
LEAD_TIME_DIAS = 4
COBERTURA_MESES = 1.0   # admite fracciones (p.ej. 0.5)
VENTA_DIAS_SEMANA = 6
DIAS_VENTA_X_MES = int(VENTA_DIAS_SEMANA * 4.33)  # ~26 si vendes de lun a sáb
Z = 0.0  # omitido por ahora (sin stock de seguridad adicional)
ABC_UMBRAL_A = 0.80
ABC_UMBRAL_B = 0.95
XYZ_UMBRAL_X = 0.30
XYZ_UMBRAL_Y = 0.60

# ===========================
# ARCHIVOS
# ===========================
RUTA_VENTAS = "ventas.csv"          # transaccional con columnas: COD_PROD, Fecha, Cantidad, PRECIO_DESCUENTO
RUTA_INVENTARIO = "inventario.csv"  # columnas: COD_PROD, Inventario.DESCRIPCION, SALDO ACTUAL
RUTA_SALIDA_EXCEL = "resultado_analisis_compras.xlsx"


def etiqueta_es(ts: pd.Timestamp) -> str:
    """Devuelve etiqueta tipo 'sep-24' para una fecha de inicio de mes."""
    mapa = {"Jan":"ene","Feb":"feb","Mar":"mar","Apr":"abr","May":"may","Jun":"jun",
            "Jul":"jul","Aug":"ago","Sep":"sep","Oct":"oct","Nov":"nov","Dec":"dic"}
    eng = ts.strftime("%b").title()
    yy = ts.strftime("%y")
    return f"{mapa.get(eng, eng.lower())}-{yy}"


def preparar_ventas(path_csv: str) -> pd.DataFrame:
    """Lee ventas transaccionales y las agrega a nivel (COD_PROD, Mes) con Cantidad e Ingreso."""
    # Lee CSV (coma o punto y coma)
    try:
        df = pd.read_csv(path_csv, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path_csv, sep=";", encoding="utf-8-sig")

    required = {"COD_PROD", "Fecha", "Cantidad", "PRECIO_DESCUENTO"}
    if not required.issubset(df.columns):
        falt = list(required - set(df.columns))
        raise ValueError(f"Ventas requieren columnas {sorted(required)}. Faltan: {falt}")

    df["Cantidad"] = pd.to_numeric(df["Cantidad"], errors="coerce").fillna(0)
    df["PRECIO_DESCUENTO"] = pd.to_numeric(df["PRECIO_DESCUENTO"], errors="coerce").fillna(0)
    df["Fecha"] = pd.to_datetime(df["Fecha"], dayfirst=True, errors="coerce")
    if df["Fecha"].isna().all():
        raise ValueError("No se pudo interpretar 'Fecha' en ventas.")

    df["Mes"] = df["Fecha"].dt.to_period("M").to_timestamp()
    df["Ingreso"] = df["Cantidad"] * df["PRECIO_DESCUENTO"]

    return df.groupby(["COD_PROD","Mes"], as_index=False).agg(
        Cantidad=("Cantidad","sum"),
        Ingreso=("Ingreso","sum")
    )


def preparar_inventario(path_csv: str) -> pd.DataFrame:
    """Prepara inventario (sin costo). Requiere: COD_PROD, Inventario.DESCRIPCION, SALDO ACTUAL."""
    try:
        inv = pd.read_csv(path_csv, encoding="utf-8-sig")
    except Exception:
        inv = pd.read_csv(path_csv, sep=";", encoding="utf-8-sig")

    rename = {
        "Inventario.DESCRIPCION": "DESCRIPCION",
        "SALDO ACTUAL": "SALDO_ACTUAL",
    }
    inv = inv.rename(columns=rename)
    if "SALDO_ACTUAL" in inv.columns:
        inv["SALDO_ACTUAL"] = pd.to_numeric(inv["SALDO_ACTUAL"], errors="coerce").fillna(0)

    expected = ["COD_PROD","DESCRIPCION","SALDO_ACTUAL"]
    missing = [c for c in expected if c not in inv.columns]
    if missing:
        raise ValueError(f"Inventario con columnas faltantes: {missing}. Esperado: {expected}")
    return inv[expected]


def clasificar_abc(df_valor: pd.DataFrame) -> pd.DataFrame:
    """Clasificación ABC por ingresos: A hasta 80%, B hasta 95%, C resto."""
    total = df_valor["ValorConsumo"].sum()
    df_valor = df_valor.sort_values("ValorConsumo", ascending=False).reset_index(drop=True)
    df_valor["Participacion"] = df_valor["ValorConsumo"]/total if total > 0 else 0
    df_valor["ParticipacionAcum"] = df_valor["Participacion"].cumsum()

    def etiqueta(p):
        if p <= ABC_UMBRAL_A: return "A"
        elif p <= ABC_UMBRAL_B: return "B"
        else: return "C"

    df_valor["ABC"] = df_valor["ParticipacionAcum"].apply(etiqueta)
    return df_valor


def clasificar_xyz(cv: float) -> str:
    """Clasificación XYZ por coeficiente de variación."""
    if cv <= XYZ_UMBRAL_X: return "X"
    elif cv <= XYZ_UMBRAL_Y: return "Y"
    else: return "Z"


def main():
    try:
        # ======= Cargar y preparar datos =======
        ventas = preparar_ventas(RUTA_VENTAS)   # -> COD_PROD, Mes, Cantidad, Ingreso
        inv = preparar_inventario(RUTA_INVENTARIO)

        # ======= Pivotes de cantidades e ingresos =======
        pivot = ventas.pivot_table(index="COD_PROD", columns="Mes", values="Cantidad", aggfunc="sum").fillna(0)
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)

        pivot_ing = ventas.pivot_table(index="COD_PROD", columns="Mes", values="Ingreso", aggfunc="sum").fillna(0)
        pivot_ing = pivot_ing.reindex(sorted(pivot_ing.columns), axis=1)

        # Últimos 12 meses incluyendo mes en curso
        ref = pd.Timestamp.today().to_period("M").to_timestamp()
        last12 = pd.date_range(end=ref, periods=12, freq="MS")
        for c in last12:
            if c not in pivot.columns: pivot[c] = 0
            if c not in pivot_ing.columns: pivot_ing[c] = 0

        ventas_last12 = pivot[last12]
        ingresos_last12 = pivot_ing[last12]

        # ======= Métricas (cantidades) =======
        prom12 = ventas_last12.mean(axis=1)
        desv = pivot.std(axis=1, ddof=1).fillna(0)
        cv = (desv / pivot.mean(axis=1).replace(0, np.nan)).fillna(0)

        # ======= ABC por ingresos 12M =======
        ingresos_12m = ingresos_last12.sum(axis=1)
        df_valor = clasificar_abc(pd.DataFrame({
            "COD_PROD": ingresos_12m.index,
            "ValorConsumo": ingresos_12m.values
        }))

        # ======= Inventarios (Z=0.0) =======
        prom_diaria = prom12 / max(DIAS_VENTA_X_MES, 1)
        demanda_lt = prom_diaria * LEAD_TIME_DIAS
        # Si quisieras devolver a usar SS: desv_diaria = ... ; ss = Z*desv_diaria*(LEAD_TIME_DIAS**0.5)
        inv_min = (demanda_lt).fillna(0)  # + ss si reactivas stock de seguridad
        inv_obj = inv_min + (prom12 * COBERTURA_MESES)
        inv_max = inv_obj

        # ======= Resumen base =======
        resumen = (inv
                   .merge(prom12.rename("PROM_12M"), left_on="COD_PROD", right_index=True)
                   .merge(desv.rename("DesviacionEstandar"), left_on="COD_PROD", right_index=True)
                   .merge(cv.rename("CV"), left_on="COD_PROD", right_index=True)
                   .merge(df_valor[["COD_PROD","ValorConsumo","Participacion","ParticipacionAcum","ABC"]],
                          on="COD_PROD"))

        resumen["XYZ"] = resumen["CV"].apply(clasificar_xyz)
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

        # Agregar 12 meses como columnas (en español)
        colnames_last12 = [etiqueta_es(c) for c in ventas_last12.columns]
        ventas_last12.columns = colnames_last12
        resumen = resumen.merge(ventas_last12, left_on="COD_PROD", right_index=True)

        # Totales y estado
        resumen["CANT_A_COMPRAR"] = (resumen["INV_OBJETIVO"] - resumen["SALDO_ACTUAL"]).clip(lower=0).round(2)
        resumen["ESTADO"] = np.where(resumen["SALDO_ACTUAL"] < resumen["INV_MIN"], "FALTA INV.", "OK")
        resumen["TOTAL_VENTAS_12M"] = resumen[colnames_last12].sum(axis=1)

        # VALOR_VENTAS_12M = Ingresos 12M
        resumen = resumen.merge(ingresos_12m.rename("VALOR_VENTAS_12M"),
                                left_on="COD_PROD", right_index=True, how="left")
        resumen["VALOR_VENTAS_12M"] = resumen["VALOR_VENTAS_12M"].fillna(0)

        # ---------- FORMATEOS y REDONDEOS ----------
        for col in ["PROM_12M","DesviacionEstandar","INV_MIN","INV_MAX","INV_OBJETIVO",
                    "CANT_A_COMPRAR","VALOR_VENTAS_12M","ValorConsumo"]:
            if col in resumen.columns:
                resumen[col] = pd.to_numeric(resumen[col], errors="coerce").round(2)

        if "CV" in resumen.columns:
            resumen["CV"] = pd.to_numeric(resumen["CV"], errors="coerce").round(4)
        if "Participacion" in resumen.columns:
            resumen["Participacion"] = pd.to_numeric(resumen["Participacion"], errors="coerce").round(4)
        if "ParticipacionAcum" in resumen.columns:
            resumen["ParticipacionAcum"] = pd.to_numeric(resumen["ParticipacionAcum"], errors="coerce").round(4)
        # -------------------------------------------

        # ======= Escribir Excel (con defensas RangeIndex) =======
        with pd.ExcelWriter(RUTA_SALIDA_EXCEL, engine="xlsxwriter") as w:
            base = ["COD_PROD","DESCRIPCION","SALDO_ACTUAL"]
            analit = ["TOTAL_VENTAS_12M","PROM_12M","VALOR_VENTAS_12M",
                      "DesviacionEstandar","CV","ValorConsumo",
                      "Participacion","ParticipacionAcum","ABC","XYZ","ABC_XYZ",
                      "MESES_CON_VENTA_12M","DEMANDA_NIVEL",
                      "INV_MIN","INV_MAX","INV_OBJETIVO","ESTADO","CANT_A_COMPRAR"]
            cols = base + colnames_last12 + analit

            # 1) Forzar encabezados string
            to_write = resumen[cols].copy()
            to_write.columns = [str(c) for c in to_write.columns]

            to_write.to_excel(w, index=False, sheet_name="Analisis")

            workbook  = w.book
            ws = w.sheets["Analisis"]

            try:
                formato_porcentaje = workbook.add_format({'num_format': '0.00%'})
                formato_numero     = workbook.add_format({'num_format': '0.00'})
                formato_bold       = workbook.add_format({'bold': True})
                formato_mute       = workbook.add_format({'font_color': '#666666'})
                formato_box        = workbook.add_format({'border': 1})
                formato_box_bold   = workbook.add_format({'border': 1, 'bold': True})

                headers = list(to_write.columns)
                def pos(col_name: str):
                    try:
                        return int(headers.index(col_name))
                    except ValueError:
                        return None

                # Formato porcentaje para: CV, Participacion, ParticipacionAcum
                for name in ["CV","Participacion","ParticipacionAcum"]:
                    cpos = pos(name)
                    if cpos is not None:
                        ws.set_column(int(cpos), int(cpos), 12, formato_porcentaje)

                # Formato numérico para DesviacionEstandar
                dpos = pos("DesviacionEstandar")
                if dpos is not None:
                    ws.set_column(int(dpos), int(dpos), 12, formato_numero)

                # ====== Leyenda ======
                n_filas = int(to_write.shape[0])   # asegurar int
                start_row = n_filas + 3

                ws.write(start_row, 0, "Leyenda y parámetros usados", formato_bold)
                ws.write(start_row+1, 0, "Generado", formato_mute)
                ws.write(start_row+1, 1, pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))

                ws.write(start_row+2, 0, "Lead Time (días)", formato_mute)
                ws.write_number(start_row+2, 1, float(LEAD_TIME_DIAS), formato_numero)

                ws.write(start_row+3, 0, "Cobertura (meses)", formato_mute)
                ws.write_number(start_row+3, 1, float(COBERTURA_MESES), formato_numero)

                ws.write(start_row+4, 0, "Días de venta/semana", formato_mute)
                ws.write_number(start_row+4, 1, float(VENTA_DIAS_SEMANA), formato_numero)

                # ABC fijo (por ingresos 12M)
                ws.write(start_row+6, 0, "Clasificación ABC (por ingresos 12M)", formato_box_bold)
                ws.write(start_row+7, 0, "A (Alta)", formato_box)
                ws.write(start_row+7, 1, "Participación acumulada de ingresos ≤ 80%", formato_box)
                ws.write(start_row+8, 0, "B (Media)", formato_box)
                ws.write(start_row+8, 1, "80% < participación acumulada ≤ 95%", formato_box)
                ws.write(start_row+9, 0, "C (Baja)", formato_box)
                ws.write(start_row+9, 1, "Participación acumulada > 95%", formato_box)

                # XYZ según CV
                ws.write(start_row+11, 0, "Clasificación XYZ (por CV)", formato_box_bold)
                ws.write(start_row+12, 0, "X (Estables)", formato_box)
                ws.write(start_row+12, 1, f"CV ≤ {XYZ_UMBRAL_X:.2f}", formato_box)
                ws.write(start_row+13, 0, "Y (Moderadamente variables)", formato_box)
                ws.write(start_row+13, 1, f"{XYZ_UMBRAL_X:.2f} < CV ≤ {XYZ_UMBRAL_Y:.2f}", formato_box)
                ws.write(start_row+14, 0, "Z (Erráticos)", formato_box)
                ws.write(start_row+14, 1, f"CV > {XYZ_UMBRAL_Y:.2f}", formato_box)

                ws.write(start_row+16, 0, "Nota", formato_bold)
                ws.write(start_row+17, 0, "CV, Participación y Participación acumulada se muestran como porcentaje en Excel.", formato_mute)

            except Exception:
                # Si algo del formato falla, seguimos generando el archivo sin aplicar estilos.
                pass

        print(f"OK: se generó {Path(RUTA_SALIDA_EXCEL).resolve()}")

    except Exception as e:
        print("[ERROR]", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

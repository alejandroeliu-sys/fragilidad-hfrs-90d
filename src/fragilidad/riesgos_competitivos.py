"""Riesgos competitivos: reingreso y urgencias a 90 días, con la muerte como competidora."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2

from fragilidad.supervivencia import ORDEN_CATEGORIA, asignar_terciles
from fragilidad.tabla1 import formatear_p

DESENLACES = {"reingreso": "Reingreso", "urgencias": "Visita a urgencias"}


def codificar_eventos(df, evento):
    """Tipo 1 = el evento llegó primero, 2 = la muerte llegó primero, 0 = censura.

    Si el evento y la muerte caen el mismo día, cuenta el evento (tipo 1).
    Sin evento ni muerte, el tiempo es el mínimo entre dias_seguimiento y 90.
    """
    df = df.copy()
    dias_ev, dias_m = df[f"dias_{evento}"], df["dias_muerte"]
    primero_ev = dias_ev.notna() & (dias_m.isna() | (dias_ev <= dias_m))
    primero_m = dias_m.notna() & ~primero_ev
    df["tipo"] = np.select([primero_ev, primero_m], [1, 2], default=0)
    censura = np.minimum(df["dias_seguimiento"], 90)
    df["tiempo"] = np.select([primero_ev, primero_m], [dias_ev, dias_m], default=censura)
    return df


def incidencia_acumulada(tiempo, tipo, causa=1):
    """Aalen-Johansen: incidencia acumulada de 'causa' en cada día con algún dato."""
    datos = pd.DataFrame({"t": tiempo, "dc": tipo == causa, "d": tipo > 0})
    tabla = datos.groupby("t").agg(n=("d", "size"), dc=("dc", "sum"), d=("d", "sum"))
    en_riesgo = tabla["n"][::-1].cumsum()[::-1]  
    sobrevida_previa = (1 - tabla["d"] / en_riesgo).cumprod().shift(fill_value=1.0)
    return (sobrevida_previa * tabla["dc"] / en_riesgo).cumsum()


def cif_al_dia(cif, dia):
    """Valor de la curva escalonada en un día (0 si aún no hay eventos)."""
    previos = cif[cif.index <= dia]
    return float(previos.iloc[-1]) if len(previos) else 0.0


def prueba_gray(tiempo, tipo, grupo):
    """Prueba de Gray (1988): ¿difiere la incidencia acumulada del tipo 1 entre grupos?

    Traducción de la subrutina crst de cmprsk::cuminc (R) con rho = 0 y un estrato.
    Devuelve el estadístico chi cuadrada, los grados de libertad (grupos - 1) y p.
    """
    t, m = np.asarray(tiempo, float), np.asarray(tipo, int)
    _, g = np.unique(np.asarray(grupo), return_inverse=True)
    k = g.max() + 1
    if k < 2:
        return None
    rs = np.bincount(g, minlength=k).astype(float)  
    f1m, skmm, fm = np.zeros(k), np.ones(k), 0.0  
    s, v = np.zeros(k - 1), np.zeros((k - 1, k - 1))  
    c, v2, v3 = np.zeros((k, k)), np.zeros((k - 1, k)), np.zeros(k)
    with np.errstate(divide="ignore", invalid="ignore"):
        for ti in np.unique(t):
            hoy = t == ti
            d1 = np.bincount(g[hoy & (m == 1)], minlength=k)
            d2 = np.bincount(g[hoy & (m == 2)], minlength=k)
            n1, vivo = d1.sum(), rs > 0
            if n1 + d2.sum() > 0:
                skm = np.where(vivo, skmm * (rs - d1 - d2) / rs, skmm)
                f1 = np.where(vivo, f1m + skmm * d1 / rs, f1m)
                h = np.where(vivo, rs / skmm, 0.0)  
                tr, tq = h.sum(), (h * (1 - f1m)).sum()
                f = fm + n1 / tr
                a = np.diag(h) - np.outer(h, h) / tr
                c += a * n1 / (tr * (1 - fm))
                s += (d1 - n1 * h * (1 - f1m) / tq)[: k - 1]  
                # Varianza: aporte de los eventos de tipo 1
                if n1 > 0:
                    t4 = np.where(skm > 0, 1 - (1 - f) / skm, 1.0)
                    t5 = 1 - (n1 - 1) / (tr * skmm - 1) if n1 > 1 else 1.0
                    t3 = np.where(vivo, t5 * skmm * n1 / (tr * rs), 0.0)
                    b = a[: k - 1] - c[: k - 1] * t4
                    v3 += t4**2 * t3
                    v2 += b * t4 * t3
                    v += (b * t3) @ b.T
                # Varianza: aporte de las muertes (tipo 2)
                ok = (skm > 0) & (d2 > 0)
                t4 = np.where(ok, (1 - f) / skm, 0.0)
                t5 = np.where(d2 > 1, 1 - (d2 - 1) / (rs - 1), 1.0)
                t3 = np.where(ok, t5 * skmm**2 * d2 / rs**2, 0.0)
                b = c[: k - 1] * t4
                v3 += t4**2 * t3
                v2 -= b * t4 * t3
                v += (b * t3) @ b.T
                fm, f1m, skmm = f, f1, skm
            rs -= np.bincount(g[hoy], minlength=k) 
    cr = c[: k - 1]
    v += (cr * v3) @ cr.T + cr @ v2.T + v2 @ cr.T
    estadistico = float(s @ np.linalg.solve(v, s))
    return {"estadistico": estadistico, "gl": int(k - 1), "p": float(chi2.sf(estadistico, k - 1))}


def graficar_cif(df, columna, orden, ruta, titulo):
    """Curvas de incidencia acumulada: evento (línea continua) y muerte (punteada)."""
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 6))
    for i, grupo in enumerate(orden):
        sub = df[df[columna] == grupo]
        if sub.empty:
            continue
        for causa, estilo, texto in [(1, "-", "evento"), (2, ":", "muerte")]:
            cif = incidencia_acumulada(sub["tiempo"], sub["tipo"], causa)
            x, y = np.r_[0, cif.index], np.r_[0, cif.values]
            ax.step(x, y, where="post", ls=estilo, color=f"C{i}",
                    label=f"{grupo} (n={len(sub)}), {texto}")
    ax.set(xlim=(0, 90), xticks=[0, 30, 60, 90], ylim=(0, None), title=titulo,
           xlabel="Días desde el egreso", ylabel="Incidencia acumulada")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def resumir(df, columna, orden):
    """Por grupo: n, eventos, muertes primero e incidencia a 30 y 90 días."""
    filas = []
    for grupo in orden:
        sub = df[df[columna] == grupo]
        if sub.empty:
            continue
        cif = incidencia_acumulada(sub["tiempo"], sub["tipo"], 1)
        cif_m = incidencia_acumulada(sub["tiempo"], sub["tipo"], 2)
        filas.append(
            f"| {grupo} | {len(sub):,} | {(sub['tipo'] == 1).sum():,} | "
            f"{(sub['tipo'] == 2).sum():,} | {100 * cif_al_dia(cif, 30):.1f} | "
            f"{100 * cif_al_dia(cif, 90):.1f} | {100 * cif_al_dia(cif_m, 90):.1f} |"
        )
    return filas


def texto_gray(res):
    if res is None:
        return "— | — | — (menos de 2 grupos)"
    return f"{res['estadistico']:.2f} | {res['gl']} | {formatear_p(res['p'])}"


def analizar(desenlaces, hfrs):
    """Une los CSV, corre todo y devuelve el Markdown."""
    df = desenlaces.merge(hfrs[["person_id", "hfrs", "categoria"]], on="person_id")
    df["tercil"], _, n_terciles = asignar_terciles(df["hfrs"])
    orden_terciles = [f"T{i}" for i in range(1, n_terciles + 1)]
    lineas = [
        "# Riesgos competitivos a 90 días según el HFRS",
        "",
        f"Personas: {len(df):,}. Día 0 = egreso. Tipo 1 = el evento llegó primero; "
        "tipo 2 = la muerte llegó primero (riesgo competitivo); tipo 0 = censura "
        "en el mínimo entre `dias_seguimiento` y 90. Si el evento y la muerte caen "
        "el mismo día, cuenta el evento. La incidencia acumulada es la de "
        "Aalen-Johansen y la comparación entre grupos, la prueba de Gray (rho = 0, "
        "como `cmprsk::cuminc` en R).",
    ]
    for evento, nombre in DESENLACES.items():
        d = codificar_eventos(df, evento)
        graficar_cif(d, "categoria", ORDEN_CATEGORIA, f"figuras/cif_{evento}.png",
                     f"{nombre} a 90 días con la muerte como riesgo competitivo")
        lineas += [
            "", f"## {nombre}", "", f"![Incidencia acumulada](../figuras/cif_{evento}.png)", "",
            "| Grupo | n | Eventos | Muertes primero | % a 30 días | % a 90 días | % muerte a 90 días |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        lineas += resumir(d, "categoria", ORDEN_CATEGORIA) + resumir(d, "tercil", orden_terciles)
        lineas += [
            "", "| Prueba de Gray | Estadístico | gl | p |", "|---|---:|---:|---:|",
            f"| Categorías HFRS | {texto_gray(prueba_gray(d['tiempo'], d['tipo'], d['categoria']))} |",
            f"| Terciles (sensibilidad) | {texto_gray(prueba_gray(d['tiempo'], d['tipo'], d['tercil']))} |",
        ]
    n_alto = int((df["categoria"] == ">15").sum())
    lineas += [
        "", "## Limitaciones", "",
        f"El grupo >15 tiene {n_alto} personas, así que su curva es inestable. "
        f"Los terciles salieron en {n_terciles} grupo(s) por los empates del HFRS. "
        "La prueba de Gray compara las incidencias acumuladas, no las tasas "
        "de evento entre quienes siguen vivos.", "",
    ]
    return "\n".join(lineas)


if __name__ == "__main__":
    desenlaces = pd.read_csv("data/desenlaces_cohorte.csv")
    hfrs = pd.read_csv("data/hfrs_cohorte.csv")
    markdown = analizar(desenlaces, hfrs)
    Path("docs").mkdir(exist_ok=True)
    Path("docs/riesgos_competitivos.md").write_text(markdown, encoding="utf-8")
    print(markdown)

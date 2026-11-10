"""Diagrama de flujo de inclusión (estilo CONSORT/STROBE)"""
import sys
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fragilidad.atricion import contar_atricion


def dibujar_flujo(tabla, salida="figuras/flujo_cohorte.png"):
    """Dibuja una caja por paso y, a la derecha, cuántos se perdieron."""
    n_pasos = len(tabla)
    fig, ax = plt.subplots(figsize=(9, 1.1 * n_pasos))
    ax.axis("off")
    for i, fila in tabla.iterrows():
        y = n_pasos - i
        ax.text(0.35, y, f"{fila['paso']}\nn = {fila['n']:,}", ha="center", va="center",
                fontsize=9, bbox=dict(boxstyle="round", facecolor="#e8f0fe"))
        if i > 0:
            ax.annotate("", xy=(0.35, y + 0.3), xytext=(0.35, y + 0.7),
                        arrowprops=dict(arrowstyle="->"))
            if fila["perdidos"] > 0:
                ax.text(0.8, y + 0.5, f"Excluidos: {fila['perdidos']:,}", ha="center",
                        va="center", fontsize=8, bbox=dict(boxstyle="square", facecolor="#fde8e8"))
    ax.set_xlim(0, 1)
    ax.set_ylim(0.3, n_pasos + 0.7)
    fig.savefig(salida, dpi=200, bbox_inches="tight")
    return salida


if __name__ == "__main__":
    con = duckdb.connect(sys.argv[1], read_only=True)
    tabla = contar_atricion(con, open("sql/02_cohorte.sql").read())
    print("Guardado en", dibujar_flujo(tabla))

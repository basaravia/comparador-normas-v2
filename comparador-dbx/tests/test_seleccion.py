"""backend/retrieval/seleccion.py: selección de las secciones que se comparan sobre la tabla de recuperación (RF-08, RF-09)."""
import pandas as pd
import pytest

from backend.retrieval import seleccion as S
from backend.retrieval.tabla import COLUMNAS


def fila(doc, id_, ident, ruta="", rol="se compara (hoja)", titulo="", incluir="✔", motivo=""):
    base = dict.fromkeys(COLUMNAS, "")
    base.update(Documento=doc, Id=id_, Identificador=ident, Ruta=ruta, Rol=rol, Título=titulo, Incluir=incluir, Motivo=motivo, **{"Sub-chunks": 1})
    return base


@pytest.fixture
def tabla():
    return pd.DataFrame([
        fila("M", "m1", "I", rol="excluida (hoja)", titulo="INTRODUCCIÓN", incluir="✘", motivo="preámbulo"),
        fila("M", "m5", "V", rol="agrupa", titulo="LINEAMIENTOS"),
        fila("M", "m5a", "5.1", ruta="V", titulo="Conocimiento del cliente"),
        fila("M", "m5b", "5.2", ruta="V", titulo="Debida diligencia"),
        fila("M", "m5b1", "5.2.1", ruta="V › 5.2", titulo="Beneficiario final"),
        fila("M", "m12", "12.1", ruta="XII", rol="excluida (hoja)", titulo="Anexo matriz", incluir="✘", motivo="anexo"),
        fila("N", "n1", "Art. 1", titulo="Objeto"), fila("N", "n2", "Art. 2", titulo="Ámbito")])


def test_ids_seleccionados_son_las_hojas_incluidas(tabla):
    assert S.ids_seleccionados(tabla) == {"m5a", "m5b", "m5b1", "n1", "n2"}


def test_marcar_un_padre_marca_todos_sus_hijos(tabla):
    t = S.excluir(tabla, ids=["m5"])
    assert S.ids_seleccionados(t) == {"n1", "n2"}                       # 5.1, 5.2 y 5.2.1 cuelgan de V
    assert set(t.loc[t["Id"].isin(["m5a", "m5b", "m5b1"]), "Motivo"]) == {"excluida por el auditor"}
    assert S.ids_seleccionados(S.reincluir(t, ids=["m5"])) == S.ids_seleccionados(tabla)


def test_un_padre_con_el_mismo_identificador_en_otro_documento_no_se_toca(tabla):
    otra = pd.concat([tabla, pd.DataFrame([fila("OTRO", "o1", "5.1", ruta="V")])], ignore_index=True)
    assert "o1" in S.ids_seleccionados(S.excluir(otra, ids=["m5"]))


def test_reincluir_un_anexo_lo_pone_en_la_comparacion(tabla):
    t = S.reincluir(tabla, ids=["m12"])
    assert "m12" in S.ids_seleccionados(t) and t.loc[t["Id"] == "m12", "Motivo"].iloc[0] == "reincluida por el auditor"
    assert t.loc[t["Id"] == "m12", "Rol"].iloc[0] == "se compara (hoja)"
    assert tabla.loc[tabla["Id"] == "m12", "Incluir"].iloc[0] == "✘"      # la tabla original no cambia


def test_el_buscador_marca_por_titulo_o_identificador_sin_distinguir_mayusculas(tabla):
    assert S.ids_seleccionados(S.excluir(tabla, texto="diligencia")) == {"m5a", "m5b1", "n1", "n2"}
    assert "m5a" not in S.ids_seleccionados(S.excluir(tabla, texto="5.1"))


def test_un_contenedor_nunca_entra_a_ids_seleccionados(tabla):
    assert "m5" not in S.ids_seleccionados(S.reincluir(tabla, ids=["m5"]))


def test_contadores_por_documento(tabla):
    c = S.contadores(tabla)
    assert dict(c.loc["M"]) == {"hojas": 5, "incluidas": 3, "excluidas": 2, "sub_chunks": 3} and dict(c.loc["N"])["incluidas"] == 2


def test_estimar_pares_usa_solo_las_hojas_incluidas(tabla):
    norma, manual = tabla[tabla["Documento"] == "N"], tabla[tabla["Documento"] == "M"]
    assert S.estimar_pares(norma, manual) == 2 * 3
    assert S.estimar_pares(norma, S.reincluir(manual, ids=["m1", "m12"])) == 2 * 5


def test_excluidas_lista_las_hojas_no_comparadas_con_su_motivo(tabla):
    x = S.excluidas(tabla)
    assert list(x["Identificador"]) == ["I", "12.1"] and list(x["Motivo"]) == ["preámbulo", "anexo"]


def test_solo_incluidas_filtra_los_objetos_seccion_conservando_el_orden(tabla):
    class Sec:
        def __init__(self, id): self.id = id
    secs = [Sec(i) for i in ("m1", "m5a", "m12", "m5b")]
    assert [s.id for s in S.solo_incluidas(secs, tabla)] == ["m5a", "m5b"]


def test_resumen_exclusion_cuenta_por_categoria(tabla):
    assert S.resumen_exclusion(tabla) == "Se excluyeron 2 secciones que no son cuerpo del documento (preámbulo: 1, anexo: 1)."
    heredada = tabla.copy(); heredada.loc[heredada["Id"] == "m12", "Motivo"] = "anexo (hereda de XII)"
    assert "anexo: 1" in S.resumen_exclusion(heredada)                         # la herencia cuenta en su categoría
    assert S.resumen_exclusion(S.reincluir(tabla, ids=["m1", "m12"])) == "No se excluyó ninguna sección."


def test_avisos_si_se_excluye_mucho_o_una_exclusion_arrastra_demasiado():
    filas = [fila("M", "cap", "XII", rol="agrupa", titulo="ANEXOS")]
    filas += [fila("M", f"h{i}", f"12.{i}", ruta="XII", rol="excluida (hoja)", incluir="✘", motivo="anexo (hereda de XII)") for i in range(12)]
    filas += [fila("M", f"b{i}", f"5.{i}", ruta="V") for i in range(8)]
    t = pd.DataFrame(filas)
    a = S.avisos_exclusion(t, max_pct=25, max_heredadas=10)
    assert len(a) == 2 and "60 %" in a[0] and "12 de 20" in a[0] and "«XII» arrastra 12 secciones" in a[1]
    assert S.avisos_exclusion(t, max_pct=70, max_heredadas=20) == []


def test_sin_exclusiones_no_hay_avisos(tabla):
    assert S.avisos_exclusion(S.reincluir(tabla, ids=["m1", "m12"])) == []

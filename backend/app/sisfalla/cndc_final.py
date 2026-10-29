"""Subquery compartida: fallas cuyo informe FINAL o RECTIFICATORIO del CNDC
ya fue emitido (dossier §3a; reportes.py:566-599 de SisFalla_30X64).

De los informes emitidos de una falla, se queda con el de mayor tipo (el
rectificatorio desplaza al final) — un final en elaboración no cuenta, y un
rectificatorio en borrador no desplaza al final ya emitido.
"""
from .constants import PK_COD_CNDC
from .dominios import codigos

CNDC_FINAL_SUBQUERY = """
    (SELECT cf_inf.PK_COD_FALLA, MAX(cf_inf.PK_D_COD_TIPOINFORME) AS MAX_TIPO
     FROM F_GF_INFORMEFALLA cf_inf
     WHERE cf_inf.PK_ORIGEN_INFORME = :cf_cndc
       AND cf_inf.PK_D_COD_TIPOINFORME IN (:cf_tfinal, :cf_trectif)
       AND cf_inf.D_COD_ESTADO_INF IN (:cf_eenv, :cf_eapr)
     GROUP BY cf_inf.PK_COD_FALLA)
"""


def cndc_final_binds() -> dict:
    c = codigos()
    return {
        "cf_cndc": PK_COD_CNDC,
        "cf_tfinal": c.tipo_final,
        "cf_trectif": c.tipo_rectificatorio,
        "cf_eenv": c.estado_enviado,
        "cf_eapr": c.estado_aprobado,
    }

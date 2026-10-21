import json

import pytest

from cwbdatasiac.config import EXPECTED_COLUMNS, IngestSettings

HEADER = ";".join(EXPECTED_COLUMNS) + ";"
ROW = (
    "Solicitação;Secretaria Municipal do Meio Ambiente;23/07/2026;Coleta;Entulhos;Concluído;"
    "Rua Exemplo;XAXIM;Unidade Regional Boqueirao;31/07/2026;App 156;"
)


def make_csv(rows: int = 5, header: str = HEADER, bom: bool = True, row: str = ROW) -> bytes:
    """CSV sintético no formato da fonte: BOM UTF-8, CRLF e ';' no fim de cada linha."""
    text = "\r\n".join([header, *[row] * rows]) + "\r\n"
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


def make_manifest(*names: str) -> str:
    dados = "\n".join(f'<dado nome="156" arquivo="{n}" />' for n in names)
    return f"<dadosabertos><conjunto><dados>{dados}</dados></conjunto></dadosabertos>"


def make_portal_payload(*names: str, sucesso: bool = True) -> str:
    rows = "".join(
        f"<tr><td><a href='https://mid-dadosabertos.curitiba.pr.gov.br/156/{n}'>{n}</a></td></tr>"
        for n in names
    )
    return json.dumps({"sucesso": sucesso, "tabela": f"<table>{rows}</table>", "erro": ""})


@pytest.fixture
def settings(tmp_path):
    return IngestSettings(
        data_dir=tmp_path / "data", min_bytes=10, retry_wait_s=0, use_browser=False
    )

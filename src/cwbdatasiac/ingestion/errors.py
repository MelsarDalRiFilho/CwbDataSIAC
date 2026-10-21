class IngestionError(Exception):
    """Falha de uma etapa da ingestão. `etapa` vai para o log e para `ingestao_execucoes`."""

    etapa = "ingestao"

    def __init__(self, message: str, *, quarantine: bool = False) -> None:
        super().__init__(message)
        self.quarantine = quarantine


class DiscoveryError(IngestionError):
    etapa = "descoberta"


class DownloadError(IngestionError):
    etapa = "download"


class CheckError(IngestionError):
    def __init__(self, etapa: str, message: str, *, quarantine: bool = True) -> None:
        super().__init__(message, quarantine=quarantine)
        self.etapa = etapa

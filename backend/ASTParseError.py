class ASTParseError(Exception):
    def __init__(self, message: str, filename: str | None, lineno: int | None,
                 col: int | None):
        parts = []
        if filename:
            parts.append(f'File "{filename}"')
        if lineno is not None:
            parts.append(f"line {lineno}")
        if col is not None:
            parts.append(f"col {col}")
        prefix = (": ".join([", ".join(parts), message]) if parts else message)
        super().__init__(prefix)
        self.filename = filename
        self.lineno = lineno
        self.col = col

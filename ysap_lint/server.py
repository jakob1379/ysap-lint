import traceback

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from . import __version__
from .linter import lint

server = LanguageServer("ysap-lint", __version__)


def _validate(ls: LanguageServer, uri: str) -> None:
    doc = ls.workspace.get_text_document(uri)
    try:
        found = lint(doc.source)
    except Exception:
        # stale diagnostics for text that is gone are worse than none
        found = []
        ls.window_log_message(types.LogMessageParams(
            types.MessageType.Error, traceback.format_exc()))
    diagnostics = [
        types.Diagnostic(
            range=doc.range_to_client_units(types.Range(
                start=types.Position(line=d.line, character=d.col),
                end=types.Position(line=d.end_line, character=d.end_col))),
            message=d.message,
            code=d.code,
            severity=(types.DiagnosticSeverity.Error
                      if d.code == "YS405"
                      else types.DiagnosticSeverity.Warning),
            source="ysap-lint")
        for d in found
    ]
    ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
        uri=uri, version=doc.version, diagnostics=diagnostics))


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: types.DidOpenTextDocumentParams):
    _validate(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: LanguageServer, params: types.DidChangeTextDocumentParams):
    _validate(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: LanguageServer, params: types.DidCloseTextDocumentParams):
    ls.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
        uri=params.text_document.uri, diagnostics=[]))

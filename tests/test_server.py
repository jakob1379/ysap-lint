import json
import subprocess
import sys
import threading

import pytest


class Client:
    def __init__(self, proc):
        self.proc = proc

    def send(self, method, params, id=None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if id is not None:
            msg["id"] = id
        body = json.dumps(msg).encode()
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n%s" % (len(body), body))
        self.proc.stdin.flush()

    def read(self):
        length = 0
        while (line := self.proc.stdout.readline().strip()):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":")[1])
        assert length, "server closed the connection"
        return json.loads(self.proc.stdout.read(length))

    def diagnostics(self):
        while True:
            msg = self.read()
            if msg.get("method") == "textDocument/publishDiagnostics":
                return msg["params"]["diagnostics"]


@pytest.fixture
def client():
    proc = subprocess.Popen(
        [sys.executable, "-m", "ysap_lint.cli", "server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    watchdog = threading.Timer(20, proc.kill)
    watchdog.start()
    c = Client(proc)
    c.send("initialize", {"processId": None, "rootUri": None,
                          "capabilities": {}}, id=1)
    while c.read().get("id") != 1:
        pass
    c.send("initialized", {})
    yield c
    watchdog.cancel()
    proc.kill()
    proc.wait()


def test_diagnostics_follow_the_document(client):
    uri = "file:///tmp/x.sh"
    client.send("textDocument/didOpen", {"textDocument": {
        "uri": uri, "languageId": "shellscript", "version": 1,
        "text": "echo 'héllo' $x\n"}})
    (diag,) = client.diagnostics()
    assert diag["code"] == "YS501"
    assert diag["source"] == "ysap-lint"
    assert diag["range"] == {"start": {"line": 0, "character": 13},
                             "end": {"line": 0, "character": 15}}

    client.send("textDocument/didChange", {
        "textDocument": {"uri": uri, "version": 2},
        "contentChanges": [{"text": "echo 'héllo' \"$x\"\n"}]})
    assert client.diagnostics() == []


def test_half_typed_code_does_not_kill_the_server(client):
    uri = "file:///tmp/y.sh"
    client.send("textDocument/didOpen", {"textDocument": {
        "uri": uri, "languageId": "shellscript", "version": 1,
        "text": 'f() {\n\tlocal\n\tif [[ $(( "\n'}})
    client.diagnostics()
    client.send("textDocument/didChange", {
        "textDocument": {"uri": uri, "version": 2},
        "contentChanges": [{"text": "cd /tmp\n"}]})
    assert [d["code"] for d in client.diagnostics()] == ["YS403"]


def test_close_clears_diagnostics(client):
    uri = "file:///tmp/z.sh"
    client.send("textDocument/didOpen", {"textDocument": {
        "uri": uri, "languageId": "shellscript", "version": 1,
        "text": "cd /tmp\n"}})
    assert len(client.diagnostics()) == 1
    client.send("textDocument/didClose", {"textDocument": {"uri": uri}})
    assert client.diagnostics() == []

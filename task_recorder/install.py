"""Explicit Windows setup: prepare first, switch code atomically, retain rollback."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .release import activate, atomic_text, prepare, rollback


def connection(data):
    path = Path(data) / "connection.json"
    if not path.exists():
        return None
    from .windows import protect
    config = json.loads(path.read_text(encoding="utf-8"))
    site = config["origin"]
    parsed = urlsplit(site)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or site != "http://127.0.0.1:" + str(parsed.port):
        raise ValueError("The installed recorder connection is not a valid loopback address.")
    key = protect(bytes.fromhex(config["protected"]), True).decode()
    return site, key


def state_at(site, key):
    with urlopen(Request(site + "/api/state", headers={"X-Recorder-Key":key}), timeout=2) as response:
        return json.load(response)


def recorder_inactive(data):
    """The helper owns this lock for its full lifetime, including shutdown."""
    lock = Path(data) / "recorder.lock"
    if os.name != "nt" or not lock.is_file():
        return False
    from .server import instance_lock
    try:
        with instance_lock(lock):
            return True
    except (OSError, RuntimeError):
        return False


def stop_idle(data):
    if recorder_inactive(data):
        return
    current = connection(data)
    if not current:
        return
    site, key = current
    try:
        state = state_at(site, key)
    except URLError as error:
        if isinstance(error.reason, ConnectionRefusedError) or getattr(error.reason, "winerror", None) == 10061:
            return
        raise RuntimeError("Could not confirm the installed recorder is idle. Close it before updating.") from error
    if state["mode"] in {"recording", "recording_paused", "running", "paused", "pausing", "starting", "uncertain"}:
        raise RuntimeError("Stop the current recorder task before updating or rolling back.")
    with urlopen(Request(site + "/api/shutdown", data=b"{}", headers={"X-Recorder-Key":key,"Content-Type":"application/json"}), timeout=15):
        pass
    for _ in range(50):
        if recorder_inactive(data):
            return
        try:
            state_at(site, key)
        except ConnectionResetError:
            # Windows may reset a poll accepted just before our authenticated
            # shutdown closes the listener. Keep checking until refusal proves
            # it has exited; a reset alone never authorizes switching code.
            pass
        except URLError as error:
            if isinstance(error.reason, ConnectionRefusedError) or getattr(error.reason, "winerror", None) == 10061:
                return
            if not (isinstance(error.reason, ConnectionResetError) or getattr(error.reason, "winerror", None) == 10054):
                raise
        time.sleep(.1)
    raise RuntimeError("The previous recorder did not shut down. Its selected release was retained.")


LAUNCHER = '''Option Explicit
Dim fs, sh, base, selected, folder, flag, pattern
Set fs = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.Environment("Process").Remove "SPORTS_CAVE_RECORDER_SOURCE"
sh.Environment("Process").Remove "PYTHONPATH"
sh.Environment("Process").Remove "PYTHONHOME"
base = fs.GetParentFolderName(WScript.ScriptFullName)
selected = "legacy"
If fs.FileExists(base & "\\active.txt") Then selected = Trim(fs.OpenTextFile(base & "\\active.txt", 1).ReadLine)
folder = base
If selected <> "legacy" Then
 Set pattern = New RegExp
 pattern.Pattern = "^([a-f0-9]{20}|[a-f0-9]{64})$"
 If Not pattern.Test(selected) Then WScript.Quit 2
 folder = base & "\\releases\\" & selected
End If
flag = ""
If WScript.Arguments.Count > 0 Then flag = WScript.Arguments(0)
Select Case flag
 Case "", "--shutdown", "--open", "--pair", "--toolbar"
 Case Else: WScript.Quit 2
End Select
sh.CurrentDirectory = folder & "\\app"
sh.Run Chr(34) & folder & "\\venv\\Scripts\\pythonw.exe" & Chr(34) & " -B -m task_recorder.server " & flag, 0, False
'''


def write_launchers(install):
    install = Path(install)
    atomic_text(install / "Start.vbs", LAUNCHER.replace("\n", "\r\n"))
    for name, flag in (("Start", ""), ("Stop", "--shutdown"), ("Diagnostics", "--open"), ("Connect PC", "--pair")):
        atomic_text(install / (name + ".cmd"), '@echo off\r\nwscript.exe "%~dp0Start.vbs" ' + flag + '\r\n')
    atomic_text(install / "Rollback.ps1", '''$ErrorActionPreference = 'Stop'
$release = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'active.txt') -Raw).Trim()
if ($release -eq 'legacy') { $release = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'previous.txt') -Raw).Trim() }
if ($release -notmatch '^([a-f0-9]{20}|[a-f0-9]{64})$') { throw 'No reviewed rollback installer is available.' }
$folder = Join-Path $PSScriptRoot ('releases\\' + $release)
Push-Location (Join-Path $folder 'app')
try { & (Join-Path $folder 'venv\\Scripts\\python.exe') -B -m task_recorder.install --rollback; if ($LASTEXITCODE -ne 0) { throw 'Rollback did not complete.' } }
finally { Pop-Location }
''')
    atomic_text(install / "Rollback.cmd", '@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Rollback.ps1"\r\nif errorlevel 1 pause\r\n')


def shortcuts(install, menu, run):
    menu.mkdir(parents=True, exist_ok=True)
    script = install / "shortcuts.ps1"
    atomic_text(script, '''param($Install,$Menu)
$Shell = New-Object -ComObject WScript.Shell
foreach ($Item in @(@('Task Recorder','Start.vbs'),@('Stop Task Recorder','Stop.cmd'),@('Recorder Diagnostics','Diagnostics.cmd'),@('Connect Recorder PC','Connect PC.cmd'),@('Rollback Recorder','Rollback.cmd'))) {
 $Shortcut = $Shell.CreateShortcut((Join-Path $Menu ($Item[0]+'.lnk')))
 $Shortcut.TargetPath = Join-Path $Install $Item[1]
 $Shortcut.WorkingDirectory = $Install
 $Shortcut.WindowStyle = 7
 $Shortcut.Save()
}
''')
    run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(install), str(menu)])


def launch(install):
    subprocess.Popen(["wscript.exe", str(install / "Start.vbs")], creationflags=subprocess.CREATE_NO_WINDOW)


def wait_ready(data):
    for _ in range(40):
        try:
            current = connection(data)
            if current:
                state = state_at(*current)
                if state.get("desktop_capabilities", {}).get("capture") is True:
                    return
        except (OSError, ValueError, URLError):
            pass
        time.sleep(.25)
    raise RuntimeError("Updated recorder did not publish desktop capabilities.")


def main():
    if os.name != "nt":
        raise SystemExit("The recorder helper requires Windows.")
    if sys.version_info < (3, 11):
        raise SystemExit("Setup requires Python 3.11 or newer.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--extension-id", help="Exact installed Sports Cave Edge adapter ID")
    args = parser.parse_args()
    install = Path(os.environ["LOCALAPPDATA"]) / "SportsCaveOS/TaskRecorderHelper"
    data = install.parent / "TaskRecorderV1"
    def run(argv):
        env = {key:value for key,value in os.environ.items() if key.upper() not in {"PYTHONPATH", "PYTHONHOME", "SPORTS_CAVE_RECORDER_SOURCE"}}
        subprocess.run(argv, check=True, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    if args.rollback:
        from desktop_recorder.download_install import restore_bridge
        from .release import release_path
        selected=(install/'active.txt').read_text().strip()
        stop_idle(data)
        if selected!='legacy':restore_bridge(release_path(install,selected)/'bridge-transaction.json',data)
        rollback(install, lambda:stop_idle(data))
        launch(install)
        print("Previous recorder release selected. Recordings, settings and receipts retained.")
        return
    import re
    extension=args.extension_id
    if not extension and (data/'download-bridge.json').exists():
        extension=json.loads((data/'download-bridge.json').read_text()).get('extension_id')
    if not extension or not re.fullmatch('[a-p]{32}',extension):
        raise RuntimeError('Provide --extension-id from the installed Sports Cave Edge adapter before preparing this update.')
    source=Path(__file__).resolve().parent.parent
    selected = prepare(source, install, sys.executable, run)
    write_launchers(install)
    menu = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Sports Cave Task Recorder"
    shortcuts(install, menu, run)
    previous = activate(install, selected, lambda:stop_idle(data))
    try:
        from desktop_recorder.download_install import install_bridge, restore_bridge
        from .release import release_path
        transaction=release_path(install,selected)/'bridge-transaction.json'
        install_bridge(source/'download-host/DownloadReceiptHost.exe',install,data,extension,transaction)
        launch(install)
        wait_ready(data)
    except Exception:
        if previous != "legacy" or (install / "app/task_recorder/server.py").is_file():
            stop_idle(data)
            if 'transaction' in locals():restore_bridge(transaction,data)
            rollback(install, lambda:stop_idle(data))
            launch(install)
        raise
    print("Windows Task Recorder installed. Use Developer > Task Recorder in Sports Cave OS.")
    print("Stop: " + str(install / "Stop.cmd"))
    print("Rollback: " + str(install / "Rollback.cmd"))


if __name__ == "__main__":
    main()

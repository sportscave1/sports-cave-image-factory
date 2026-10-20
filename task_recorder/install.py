"""Stable Windows installation; preserves TaskRecorderV1 data and other companions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request,urlopen

def main():
    if os.name!="nt": raise SystemExit("The recorder helper requires Windows.")
    source=Path(__file__).resolve().parent
    install=Path(os.environ["LOCALAPPDATA"])/"SportsCaveOS"/"TaskRecorderHelper"
    data=install.parent/"TaskRecorderV1"
    install.mkdir(parents=True,exist_ok=True)
    # Stop only our authenticated, idle recorder before replacing installed code.
    config=data/"connection.json"
    if config.exists():
        from .windows import protect
        try:
            connection=json.loads(config.read_text())
            key=protect(bytes.fromhex(connection["protected"]),True).decode()
            site=connection["origin"]
            if not site.startswith("http://127.0.0.1:"):raise ValueError()
            with urlopen(Request(site+"/api/state",headers={"X-Recorder-Key":key}),timeout=2) as response:
                state=json.load(response)
        except (OSError,ValueError,KeyError):state=None
        if state:
            if state["mode"] in {"recording","recording_paused","running","paused","starting"}:
                raise SystemExit("Stop the current recorder task before updating the helper.")
            with urlopen(Request(site+"/api/shutdown",data=b"{}",headers={"X-Recorder-Key":key,"Content-Type":"application/json"}),timeout=15):pass
            for _ in range(40):
                try:
                    with urlopen(Request(site+"/api/state",headers={"X-Recorder-Key":key}),timeout=.2):pass
                    time.sleep(.1)
                except OSError:break
    app=install/"app"
    (app/"task_recorder").mkdir(parents=True,exist_ok=True)
    for path in source.iterdir():
        if path.is_file() and path.suffix in {".py",".js",".css",".html",".txt"}:
            shutil.copy2(path,app/"task_recorder"/path.name)
    python=install/"venv"/"Scripts"/"python.exe"
    if not python.is_file():
        subprocess.run([sys.executable,"-m","venv",str(install/"venv")],check=True)
    subprocess.run([str(python),"-m","pip","install","-r",str(app/"task_recorder"/"requirements.txt")],check=True)
    subprocess.run([str(python),"-m","playwright","install","chromium"],check=True)
    for name,arg in [("Start",""),("Stop","--shutdown"),("Diagnostics","--open"),("Connect PC","--pair")]:
        code='@echo off\r\npushd "%~dp0app"\r\n"%~dp0venv\\Scripts\\python.exe" -m task_recorder.server '+arg+'\r\npopd\r\n'
        if name=="Start":code='@echo off\r\nwscript.exe "%~dp0Start.vbs"\r\n'
        (install/(name+".cmd")).write_text(code)
    # pythonw avoids a console during normal launch and optional Windows startup.
    (install/"Start.vbs").write_text('Set sh = CreateObject("WScript.Shell")\r\nsh.CurrentDirectory = "'+str(app)+'"\r\nsh.Run Chr(34) & "'+str(python.with_name("pythonw.exe"))+'" & Chr(34) & " -m task_recorder.server", 0, False\r\n')
    menu=Path(os.environ["APPDATA"])/"Microsoft"/"Windows"/"Start Menu"/"Programs"/"Sports Cave Task Recorder"
    menu.mkdir(parents=True,exist_ok=True)
    script=install/"shortcuts.ps1"
    script.write_text("""param($Install,$Menu)
$Shell = New-Object -ComObject WScript.Shell
foreach ($Item in @(@('Task Recorder','Start.vbs'),@('Stop Task Recorder','Stop.cmd'),@('Recorder Diagnostics','Diagnostics.cmd'),@('Connect Recorder PC','Connect PC.cmd'))) {
 $Shortcut = $Shell.CreateShortcut((Join-Path $Menu ($Item[0]+'.lnk')))
 $Shortcut.TargetPath = Join-Path $Install $Item[1]
 $Shortcut.WorkingDirectory = $Install
 $Shortcut.WindowStyle = 7
 $Shortcut.Save()
}
""")
    subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script),str(install),str(menu)],check=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    subprocess.Popen(["wscript.exe",str(install/"Start.vbs")],creationflags=subprocess.CREATE_NO_WINDOW)
    print("Task Recorder installed. Use Developer > Task Recorder in Sports Cave OS.")
    print("Local Stop: "+str(install/"Stop.cmd"))

if __name__=="__main__":main()

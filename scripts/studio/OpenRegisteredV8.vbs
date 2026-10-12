Option Explicit
Dim shell, python, helper, home, args
Set shell = CreateObject("WScript.Shell")
python = "C:\Users\hello\Documents\sports-cave-image-factory\.venv\Scripts\pythonw.exe"
helper = "C:\Users\hello\.codex\visualizations\2026\10\12\01a12f62-716b-7020-bd5c-ca5719a94467\v8\sports-cave-core-v8-os-drafts-20261012-v8\scripts\studio\companion.py"
home = "C:\Users\hello\.codex\visualizations\2026\10\12\01a12f62-716b-7020-bd5c-ca5719a94467\v8"
args = Chr(34) & python & Chr(34) & " -B " & Chr(34) & helper & Chr(34) & " open --home " & Chr(34) & home & Chr(34) & " --id app-9ca4a85e-b3f4-4c85-b61e-4eb5551d2740 --owner codex/v8-01a12f62 --browser edge --profile Default"
shell.Run args, 0, False

Option Explicit

' Double-click this file to launch Fishbot elevated without a terminal window.
Dim shell, fso, root, pythonw, host
Set shell = CreateObject("Shell.Application")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\venv\Scripts\pythonw.exe"
host = root & "\host.py"

shell.ShellExecute pythonw, Chr(34) & host & Chr(34), root, "runas", 1

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder

venvPythonw = folder & "\.venv_runtime\Scripts\pythonw.exe"
venvPython = folder & "\.venv_runtime\Scripts\python.exe"

If fso.FileExists(venvPythonw) Then
  shell.Run """" & venvPythonw & """ """ & folder & "\main.py""", 0, False
ElseIf fso.FileExists(venvPython) Then
  shell.Run """" & venvPython & """ """ & folder & "\main.py""", 0, False
Else
  shell.Run "cmd /c """ & folder & "\start_windows.bat""", 0, False
End If

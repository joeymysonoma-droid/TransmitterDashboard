' Launch ASMG TX Dashboard with no console window, then open the browser.
Option Explicit
Dim sh, fso, dir, exe, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
exe = dir & "\AsmgTxDashboard.exe"
If Not fso.FileExists(exe) Then
  MsgBox "AsmgTxDashboard.exe not found:" & vbCrLf & exe, vbCritical, "ASMG TX Dashboard"
  WScript.Quit 1
End If
cmd = """" & exe & """ --open-browser"
sh.Run cmd, 0, False

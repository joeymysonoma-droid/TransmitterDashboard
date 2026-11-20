' Stop a running ASMG TX Dashboard process.
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run "taskkill /F /IM AsmgTxDashboard.exe", 0, True

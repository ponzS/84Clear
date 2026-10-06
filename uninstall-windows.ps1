$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$answer = [System.Windows.Forms.MessageBox]::Show('是否卸载 PC Steward 电脑管家？请先关闭程序。操作日志将保留。', '卸载电脑管家', 'YesNo', 'Question')
if ($answer -ne 'Yes') { exit 1 }
if (Get-Process PCSteward -ErrorAction SilentlyContinue) { [System.Windows.Forms.MessageBox]::Show('请先关闭电脑管家，然后重新卸载。') | Out-Null; exit 1 }
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\PCSteward'
if ($PSScriptRoot -ne $installDir) { throw 'Unexpected installation path' }
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) '电脑管家.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'PC Steward') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PCSteward' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $installDir -Recurse -Force

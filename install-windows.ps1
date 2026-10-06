$ErrorActionPreference = 'Stop'
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\PCSteward'
$release = Join-Path $PSScriptRoot 'release\PCSteward'
if (!(Test-Path (Join-Path $release 'PCSteward.exe'))) { throw 'Missing release\PCSteward\PCSteward.exe' }
$existing = Get-Process PCSteward -ErrorAction SilentlyContinue
if ($existing) { throw 'Please close PC Steward before installing.' }
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Copy-Item (Join-Path $release '*') $installDir -Recurse -Force
Copy-Item (Join-Path $PSScriptRoot 'uninstall-windows.ps1') $installDir -Force
$exe = Join-Path $installDir 'PCSteward.exe'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'PC Steward'
New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
foreach ($path in @((Join-Path $desktop '电脑管家.lnk'), (Join-Path $startMenu '电脑管家.lnk'))) {
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = $installDir
    $shortcut.IconLocation = "$exe,0"
    $shortcut.Description = 'Startup, applications, caches and process management'
    $shortcut.Save()
}
$key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PCSteward'
New-Item $key -Force | Out-Null
$values = @{
    DisplayName = 'PC Steward 电脑管家'; DisplayVersion = '1.0.0'; Publisher = 'PC Steward'; InstallLocation = $installDir;
    DisplayIcon = "$exe,0"; UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$installDir\uninstall-windows.ps1`""
}
foreach ($pair in $values.GetEnumerator()) { New-ItemProperty -Path $key -Name $pair.Key -Value $pair.Value -PropertyType String -Force | Out-Null }
New-ItemProperty $key -Name EstimatedSize -Value ([int]((Get-ChildItem $installDir -Recurse -File | Measure-Object Length -Sum).Sum/1KB)) -PropertyType DWord -Force | Out-Null
Write-Output "Installed: $exe"
Write-Output "Desktop shortcut: $desktop\电脑管家.lnk"

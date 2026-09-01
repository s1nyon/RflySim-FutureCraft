param(
    [Parameter(Mandatory = $true)][string]$Output
)

# Read-only helper: capture the main RflySim3D window to a PNG file.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class CaptureWindowNative {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
[CaptureWindowNative]::SetProcessDPIAware() | Out-Null
$Process = Get-Process -Name 'RflySim3D' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $Process) { throw 'RflySim3D window not found' }
$Rect = New-Object CaptureWindowNative+RECT
if (-not [CaptureWindowNative]::GetWindowRect($Process.MainWindowHandle, [ref]$Rect)) { throw 'GetWindowRect failed' }
$Width = $Rect.Right - $Rect.Left
$Height = $Rect.Bottom - $Rect.Top
if ($Width -le 0 -or $Height -le 0) { throw 'Invalid window size' }
$Bitmap = New-Object System.Drawing.Bitmap($Width, $Height)
$Graphics = [System.Drawing.Graphics]::FromImage($Bitmap)
$Graphics.CopyFromScreen($Rect.Left, $Rect.Top, 0, 0, (New-Object System.Drawing.Size($Width, $Height)))
$Graphics.Dispose()
$OutputDir = Split-Path -Parent $Output
if ($OutputDir -and -not (Test-Path -LiteralPath $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }
$Bitmap.Save($Output, [System.Drawing.Imaging.ImageFormat]::Png)
$Bitmap.Dispose()
Write-Output "saved=$Output size=${Width}x${Height}"

param([Parameter(Mandatory = $true)][string]$ImagePath)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]

function Wait-WinRt($Operation, [Type]$ResultType) {
    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } | Select-Object -First 1
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$resolved = (Resolve-Path -LiteralPath $ImagePath).Path
$file = Wait-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolved)) ([Windows.Storage.StorageFile])
$stream = Wait-WinRt ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
$decoder = Wait-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Wait-WinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $ocr) {
    throw "Windows OCR language support is not installed."
}
$result = Wait-WinRt ($ocr.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$result.Text

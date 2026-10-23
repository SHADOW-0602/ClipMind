param(
    [Parameter(Mandatory = $true)][string]$JsonFile,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$Voice = ""
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$items = Get-Content -Raw -Encoding UTF8 $JsonFile | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($Voice -ne "") {
        $synth.SelectVoice($Voice)
    }
    $synth.Rate = 0
    $synth.Volume = 100
    $index = 0
    foreach ($item in $items) {
        $wav = Join-Path $OutputDir ("sentence-{0:D4}.wav" -f $index)
        $synth.SetOutputToWaveFile($wav)
        $synth.Speak([string]$item)
        $synth.SetOutputToNull()
        $index++
    }
}
finally {
    $synth.Dispose()
}
Write-Output "Synthesized $index sentences"

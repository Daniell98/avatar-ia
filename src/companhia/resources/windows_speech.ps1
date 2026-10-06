param([string]$TextPath, [string]$OutputPath, [string]$VoiceName)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($VoiceName) {
        $speaker.SelectVoice($VoiceName)
    } else {
        $speaker.SelectVoiceByHints(
            [System.Speech.Synthesis.VoiceGender]::NotSet,
            [System.Speech.Synthesis.VoiceAge]::NotSet,
            0, [System.Globalization.CultureInfo]::GetCultureInfo('pt-BR'))
    }
    $speaker.SetOutputToWaveFile($OutputPath)
    $speaker.Speak([System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8))
} finally {
    $speaker.Dispose()
}

$ErrorActionPreference = "Stop"

$templatePath = "C:\Users\arand\Downloads\Apresentacao_Univesp_PI4.pptx"
$outputPath = Join-Path (Get-Location) "Apresentacao_PI5_Monitoramento_Climatico.pptx"

Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression

function Escape-XmlText {
    param([string] $Text)
    return [System.Security.SecurityElement]::Escape($Text)
}

function Set-SlideTexts {
    param(
        [Parameter(Mandatory = $true)] [System.IO.Compression.ZipArchive] $Zip,
        [Parameter(Mandatory = $true)] [int] $SlideNumber,
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string[]] $Texts
    )

    $entryPath = "ppt/slides/slide$SlideNumber.xml"
    $entry = $Zip.GetEntry($entryPath)
    if ($null -eq $entry) {
        throw "Slide not found: $entryPath"
    }

    $reader = New-Object System.IO.StreamReader($entry.Open())
    $xml = $reader.ReadToEnd()
    $reader.Close()

    $script:replaceIndex = 0
    $updated = [regex]::Replace($xml, '<a:t>(.*?)</a:t>', {
        param($match)
        if ($script:replaceIndex -lt $Texts.Count) {
            $value = Escape-XmlText $Texts[$script:replaceIndex]
        }
        else {
            $value = ""
        }
        $script:replaceIndex++
        return "<a:t>$value</a:t>"
    })

    $entry.Delete()
    $newEntry = $Zip.CreateEntry($entryPath)
    $writer = New-Object System.IO.StreamWriter($newEntry.Open())
    $writer.Write($updated)
    $writer.Close()
}

if (Test-Path $outputPath) {
    Remove-Item -LiteralPath $outputPath -Force
}

Copy-Item -LiteralPath $templatePath -Destination $outputPath

$jsonPath = Join-Path (Get-Location) "scripts\pi5_slide_texts.json"
$jsonText = [System.IO.File]::ReadAllText($jsonPath, [System.Text.Encoding]::UTF8)
$slideTextObject = $jsonText | ConvertFrom-Json
$slideTexts = @{}
foreach ($property in $slideTextObject.PSObject.Properties) {
    $slideTexts[[int]$property.Name] = [string[]]$property.Value
}

$zip = [System.IO.Compression.ZipFile]::Open($outputPath, [System.IO.Compression.ZipArchiveMode]::Update)
try {
    foreach ($slideNumber in 1..9) {
        Set-SlideTexts -Zip $zip -SlideNumber $slideNumber -Texts $slideTexts[$slideNumber]
    }
}
finally {
    $zip.Dispose()
}

Write-Output $outputPath

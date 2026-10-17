$ErrorActionPreference = 'Stop'
$Repo = 'alibaki89/Bals-Sound-Garden'
$Root = $PSScriptRoot
Write-Host "Preparing $Repo" -ForegroundColor Cyan
& git --version
if ($LASTEXITCODE -ne 0) { throw 'Git not available.' }
& gh auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI not authenticated.' }
& gh auth setup-git
if ($LASTEXITCODE -ne 0) { throw 'Could not configure Git authentication via GitHub CLI.' }
$Login = & gh api user --jq '.login'
if ($LASTEXITCODE -ne 0 -or $Login -ne 'alibaki89') { throw "Wrong GitHub account: $Login" }
$Names = & gh repo list 'alibaki89' --limit 1000 --json name --jq '.[].name'
if ($LASTEXITCODE -ne 0) { throw 'Could not list GitHub repositories.' }
if ($Names -contains 'Bals-Sound-Garden') { throw "Repository already exists. No overwrite is permitted." }
if (Test-Path (Join-Path $Root '.git')) { throw 'This folder already contains a Git repository. Review it before publishing.' }
if (-not (Test-Path (Join-Path $Root 'cat_society/app.py'))) { throw 'Prepared source missing.' }
if (-not (Test-Path (Join-Path $Root 'docs/index.html'))) { throw 'Website is missing.' }
if (-not (Test-Path (Join-Path $Root 'docs/itch-gallery/SOURCES.json'))) { throw 'Original itch.io gallery not imported. Run: py .\Import-Itch-Screenshots.py' }
if (-not (Test-Path (Join-Path $Root 'LICENSE'))) { throw 'MIT license missing.' }
Write-Host ""
Write-Host "CODE LICENSE: MIT. Game art, music and screenshots have separate rights." -ForegroundColor Yellow
Write-Host "Review asset provenance in ASSET_LICENSE_REVIEW.md before publishing." -ForegroundColor Yellow
Write-Host ""
Write-Host "Will CREATE one PUBLIC GitHub repository containing Python source, bundled game assets, documents, and the GitHub Pages website." -ForegroundColor Yellow
Write-Host "No GitHub Releases or game binaries will be created."
$Confirm = Read-Host 'Type CREATE to continue, or anything else to cancel'
if ($Confirm -cne 'CREATE') { Write-Host 'Cancelled.'; exit 0 }
& git -C $Root init -b main
if ($LASTEXITCODE -ne 0) { throw 'Git init failed.' }
& git -C $Root config core.autocrlf false
& git -C $Root add --all
if ($LASTEXITCODE -ne 0) { throw 'Git add failed.' }
& git -C $Root commit -m 'Initial public source and engineering website'
if ($LASTEXITCODE -ne 0) { throw 'Git commit failed. Check your Git author identity.' }
& gh repo create $Repo --public --source $Root --remote origin --push --description 'A cozy music-making adventure with a procedural 2.5D world, music synthesis, sequencer, and persistent animal-run shop.'
if ($LASTEXITCODE -ne 0) { throw 'Repository creation/push failed. Inspect the remote before retrying.' }
& gh repo edit $Repo --homepage 'https://alibaki89.github.io/Bals-Sound-Garden/'
if ($LASTEXITCODE -ne 0) { Write-Warning 'Repository created, but homepage field could not be set.' }
Write-Host 'Repository source published. Next: Settings -> Pages -> main -> /docs -> Save' -ForegroundColor Green

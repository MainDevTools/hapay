<#
.SYNOPSIS
    Синхронізує вихідники застосунку з репо (`app-maui/`) у VS-проєкт, з якого збирається APK.

.DESCRIPTION
    У репо `app-maui/` лежать ЛИШЕ вихідники — без `.csproj`. Реальний MAUI-проєкт живе
    окремо, тож `git pull` його НЕ оновлює. Без цього кроку оператор перезбирає стару
    версію, і виглядає, ніби зміни відкотились (так двічі й сталось 2026-07-20:
    «повернувся» перемикач, не було сторінки каталогу — бо трьох нових файлів у
    VS-проєкті взагалі не існувало).

    Скрипт копіює лише ті файли, які пишемо ми, і НІКОЛИ не чіпає `.csproj`
    (пакети/версії оператор веде вручну) та згенероване (`obj/`, `bin/`, `Platforms/Android/Resources`).

.PARAMETER Target
    Тека VS-проєкту. За замовчуванням — стандартне розташування на машині оператора.

.PARAMETER DryRun
    Лише показати, що змінилось би, нічого не копіювати.

.EXAMPLE
    pwsh scripts/sync-maui.ps1
    pwsh scripts/sync-maui.ps1 -DryRun
    pwsh scripts/sync-maui.ps1 -Target "D:\інший\шлях\Hapay"
#>
[CmdletBinding()]
param(
    [string] $Target = "C:\Users\CaveMan\source\repos\Hapay\Hapay",
    [switch] $DryRun
)

$ErrorActionPreference = "Stop"

# джерело — app-maui/ поруч зі скриптом (працює з будь-якої робочої теки)
$Source = Join-Path (Split-Path $PSScriptRoot -Parent) "app-maui"

if (-not (Test-Path $Source)) {
    Write-Error "Не знайдено вихідники: $Source"
    exit 1
}
# запобіжник: не сипати файли в випадкову теку — цільова мусить бути MAUI-проєктом
if (-not (Get-ChildItem -Path $Target -Filter "*.csproj" -ErrorAction SilentlyContinue)) {
    Write-Error "У теці немає .csproj — це не схоже на VS-проєкт: $Target`nВкажи правильний шлях через -Target."
    exit 1
}

# те, що пишемо ми. Усе інше (csproj, Platforms/Android/Resources, obj, bin) — не наше.
$Dirs  = @("Models", "Services", "ViewModels", "Views", "Drawables", "Converters",
           "Platforms\Android", "Resources\AppIcon", "Resources\Splash")
$Files = @("MauiProgram.cs", "AppShell.xaml", "AppShell.xaml.cs")

$plan = [System.Collections.Generic.List[object]]::new()

function Add-Item-ToPlan([string] $rel) {
    $src = Join-Path $Source $rel
    $dst = Join-Path $Target $rel
    $state = if (-not (Test-Path $dst)) { "НОВИЙ" }
             elseif ((Get-FileHash $src -Algorithm MD5).Hash -ne (Get-FileHash $dst -Algorithm MD5).Hash) { "ОНОВЛЕНО" }
             else { "без змін" }
    $plan.Add([pscustomobject]@{ Rel = $rel; Src = $src; Dst = $dst; State = $state })
}

foreach ($d in $Dirs) {
    $sd = Join-Path $Source $d
    if (-not (Test-Path $sd)) { continue }
    Get-ChildItem -Path $sd -Recurse -File |
        ForEach-Object { Add-Item-ToPlan $_.FullName.Substring($Source.Length + 1) }
}
foreach ($f in $Files) {
    if (Test-Path (Join-Path $Source $f)) { Add-Item-ToPlan $f }
}

$changed = $plan | Where-Object { $_.State -ne "без змін" }

foreach ($i in $changed) { "{0,-10} {1}" -f $i.State, $i.Rel }

if ($changed.Count -eq 0) {
    Write-Output "Усе вже синхронне ($($plan.Count) файлів). Копіювати нічого."
    exit 0
}
if ($DryRun) {
    Write-Output "`n[DryRun] Скопіювалося б файлів: $($changed.Count). Нічого не змінено."
    exit 0
}

foreach ($i in $changed) {
    $dir = Split-Path $i.Dst -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Copy-Item -Path $i.Src -Destination $i.Dst -Force
}

# перевірка фактом: після копіювання хеші мусять збігтися
$bad = 0
foreach ($i in $changed) {
    if ((Get-FileHash $i.Src -Algorithm MD5).Hash -ne (Get-FileHash $i.Dst -Algorithm MD5).Hash) {
        Write-Output "РОЗБІЖНІСТЬ ПІСЛЯ КОПІЮВАННЯ: $($i.Rel)"; $bad++
    }
}

Write-Output "`nСинхронізовано: $($changed.Count) (усього під наглядом: $($plan.Count)); розбіжностей: $bad"
if ($bad -gt 0) { exit 1 }
Write-Output "Далі: перезбірка у VS (F5) або  dotnet build -t:Run -f net10.0-android  у теці проєкту."
Write-Output "Якщо збірка каже «file is locked by Microsoft Visual Studio» — спершу зупини дебаг у VS (Shift+F5)."

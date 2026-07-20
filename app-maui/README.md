# Хапай — мобільний застосунок (.NET MAUI / C#)

Нативний застосунок під **Android + iOS** з одного C#/XAML-коду. Клієнт read-API `hapay.today`.
Рішення власника (2026-07-19): стек **.NET MAUI** (Visual Studio, C#) замість Flutter.

> ⚠ **Windows → iOS не збереться локально** (обмеження Apple: iOS потребує macOS+Xcode).
> На Windows: **Android — так**; iOS — через Mac (Pair to Mac) або хмарний Mac-CI.
> `[оцінка]` MAUI я (LLM) генерую менш надійно за Flutter — тому код проходить
> адверсарний рев'ю, і компілятор C# ловитиме частину помилок до запуску.

## Обрані рішення (2026-07-19)

- **Фото-кеш:** вбудований (MAUI `Image` авто-кешує `UriImageSource`) — без залежностей.
- **Архітектура:** **CommunityToolkit.Mvvm** (`[ObservableProperty]`/`[RelayCommand]`).
- **Графік історії:** свій `IDrawable` на **GraphicsView** — сходинки+розриви (T12/§5.4.2).

## Як зібрати каркас (твій крок — генерує платформні папки)

MAUI-проєкт має купу платформного boilerplate (`Platforms/`, `Resources/`). Його
генерує шаблон — а я даю змістовні файли, які лягають зверху.

1. Постав робочі навантаження: у Visual Studio Installer → **«.NET Multi-platform App UI development»** (MAUI). Або CLI: `dotnet workload install maui`.
2. Створи порожній MAUI-проєкт з іменем **Hapay** (щоб неймспейси збіглися):
   - VS: **New Project → .NET MAUI App → назва `Hapay`**; або CLI:
   ```
   dotnet new maui -n Hapay -o .
   ```
   (запускай у цій папці `app-maui/`)
3. Скопіюй мої файли (Models/ Services/ ViewModels/ Views/ Drawables/ Converters/
   + MauiProgram.cs + AppShell.xaml) поверх згенерованих (замінюючи однойменні).
4. Додай пакет:
   ```
   dotnet add package CommunityToolkit.Mvvm
   ```
5. Запусти на Android (емулятор або пристрій): у VS обери Android-девайс і **F5**;
   або CLI: `dotnet build -t:Run -f net9.0-android`.

Локальний бекенд замість прода (емулятор Android → хост): у `Services/ApiService.cs`
`Base` = `http://10.0.2.2:8080`.

## ⚠ Синхронізація з VS-проєктом (робити ПЕРЕД кожною перезбіркою)

Ця тека — **лише вихідники, без `.csproj`**. APK збирається з окремого VS-проєкту
(типово `C:\Users\<user>\source\repos\Hapay\Hapay`), і **`git pull` його НЕ оновлює**.
Без копіювання оператор перезбирає стару версію — виглядає, ніби зміни відкотились
(2026-07-20 так сталось двічі: «повернувся» перемикач, не було сторінки каталогу —
трьох нових файлів у VS-проєкті просто не існувало).

```powershell
pwsh scripts/sync-maui.ps1            # скопіювати змінені + нові
pwsh scripts/sync-maui.ps1 -DryRun    # лише показати, що змінилось би
pwsh scripts/sync-maui.ps1 -Target "D:\інший\шлях\Hapay"
```

Скрипт копіює лише наші файли (`Models/ Services/ ViewModels/ Views/ Drawables/
Converters/ Platforms/Android/ Resources/{AppIcon,Splash}/` + `MauiProgram.cs`,
`AppShell.xaml{,.cs}`), звіряє хеші після копіювання і **не чіпає `.csproj`**
(пакети/версії веде оператор вручну). Нові файли `.csproj` підхопить сам — явних
`<MauiXaml Include>` там немає, працює SDK-глобінг.

Якщо збірка каже `file is locked by "Microsoft Visual Studio"` — зупини дебаг у VS
(**Shift+F5**), тоді збирай.

## Структура (мої файли)

- `Models/` — Discount, Category, HistoryPoint (System.Text.Json, snake_case);
- `Services/ApiService.cs` — HttpClient до hapay.today;
- `ViewModels/` — HomeViewModel (стрічка+фільтр+пошук+пагінація, з guard-поколінням
  проти гонки — урок Flutter-рев'ю), DetailViewModel;
- `Views/` — HomePage, DetailPage (XAML + code-behind);
- `Drawables/PriceHistoryDrawable.cs` — чесний графік (сходинки, розрив на прогалинах);
- `Converters/` — копійки→грн, %;
- `MauiProgram.cs` — DI (реєстрація сервісу/VM/сторінок); `AppShell.xaml` — навігація.

## Перед релізом у стори (не зараз)

Apple $99/рік + Mac/CI · Google Play $25 · ФОП (кошти) · privacy/support-сторінки
на hapay.today · іконка/скріншоти/рейтинги.

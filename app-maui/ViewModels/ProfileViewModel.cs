using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

public partial class ProfileViewModel : ObservableObject
{
    private readonly AuthService _auth;
    private readonly CollectorService _collector;
    private readonly ICollectScheduler _scheduler;
    private readonly PriceWatchService _priceWatch;

    [ObservableProperty] private bool _checkingDrops;
    [ObservableProperty] private string? _dropsStatus;

    public ProfileViewModel(AuthService auth, CollectorService collector,
                            ICollectScheduler scheduler, PriceWatchService priceWatch)
    {
        _auth = auth;
        _collector = collector;
        _scheduler = scheduler;
        _priceWatch = priceWatch;
        _autoCollect = CollectPrefs.AutoEnabled;   // прямо в поле — без тригера OnChanged
    }

    public string Email => _auth.Email ?? "";
    public string Role => _auth.Role;
    public bool IsCollector => _auth.IsCollector;
    public string RoleLabel => _auth.Role switch
    {
        "collector" => "Колектор",
        "moderator" => "Модератор",
        "admin" => "Адмін",
        _ => "Користувач",
    };

    [ObservableProperty] private bool _isCollecting;
    [ObservableProperty] private string? _collectStatus;

    // фоновий збір (T16 крок 2): перемикач керує WorkManager-розкладом
    [ObservableProperty] private bool _autoCollect;

    public bool AutoCollectSupported => _scheduler.IsSupported && IsCollector;
    public string TodayText => $"Сьогодні зібрано: {CollectPrefs.TodayCount()} стор.";

    partial void OnAutoCollectChanged(bool value)
    {
        CollectPrefs.SetAuto(value);
        if (value) _scheduler.Enable();
        else _scheduler.Disable();
    }

    partial void OnIsCollectingChanged(bool value) => CollectCommand.NotifyCanExecuteChanged();

    public void Refresh()
    {
        OnPropertyChanged(nameof(Email));
        OnPropertyChanged(nameof(Role));
        OnPropertyChanged(nameof(RoleLabel));
        OnPropertyChanged(nameof(IsCollector));
        OnPropertyChanged(nameof(AutoCollectSupported));
        OnPropertyChanged(nameof(TodayText));
    }

    /// На відкритті: звіряємось із сервером (актуальні email+роль). Якщо сесія мертва —
    /// AuthService уже розлогінив, тікаємо з профілю. НЕ кидає (безпечно з async void).
    public async Task RefreshAsync()
    {
        bool alive = true;
        try { alive = await _auth.RefreshFromServerAsync(); }
        catch { /* RefreshFromServerAsync не кидає, але про всяк */ }
        Refresh();                                          // показати оновлені значення
        if (!alive)
        {
            try { await Shell.Current.GoToAsync(".."); } catch { /* уже пішли */ }
        }
    }

    // збір: тягнемо HTML крамниць зі свого IP і шлемо серверу (він парсить). Лише collector+.
    [RelayCommand(CanExecute = nameof(CanCollect))]
    private async Task Collect()
    {
        IsCollecting = true;                        // блокує кнопку (CanExecute) — без подвійного запуску
        CollectStatus = "Починаю збір…";
        try
        {
            var progress = new Progress<string>(s => CollectStatus = s);   // Progress маршалить у UI-потік
            var sum = await _collector.RunAsync(progress);
            CollectStatus = sum.Errors.Count == 0
                ? $"Готово: зібрано {sum.Accepted} позицій з {sum.Pages} сторінок."
                : $"Зібрано {sum.Accepted} з {sum.Pages} стор.; помилок {sum.Errors.Count}: "
                  + string.Join("; ", sum.Errors.Take(3));
        }
        catch (UnauthorizedException)
        {
            CollectStatus = "Немає прав колектора або токен застарів — перезайди.";
        }
        catch (Exception e)
        {
            CollectStatus = "Збій збору: " + e.Message;
        }
        finally
        {
            IsCollecting = false;
        }
    }

    private bool CanCollect() => !IsCollecting;

    // юр-сторінки на hapay.today (обов'язкові для сторів) — відкриваємо в браузері
    [RelayCommand]
    private async Task OpenLink(string? url)
    {
        if (url is not null && Uri.TryCreate(url, UriKind.Absolute, out var uri))
            await Launcher.Default.OpenAsync(uri);
    }

    [RelayCommand]
    private async Task Watchlist() => await Shell.Current.GoToAsync(nameof(WatchlistPage));

    /// Ручний запуск ТІЄЇ САМОЇ перевірки, що й фоновий воркер: не чекати годину,
    /// і не гадати, чи вона працює. Корисна й користувачеві, не лише для тесту.
    [RelayCommand]
    private async Task CheckDrops()
    {
        if (CheckingDrops) return;
        CheckingDrops = true;
        DropsStatus = "Перевіряю…";
        try
        {
            var n = await _priceWatch.CheckAsync();
            DropsStatus = n > 0
                ? $"Подешевшало: {n} — глянь сповіщення"
                : "Поки без змін — нічого не подешевшало";
        }
        catch (UnauthorizedException)
        {
            DropsStatus = "Сесія застаріла — увійди ще раз";
        }
        catch (Exception e)
        {
            DropsStatus = $"Не вдалося: {e.Message}";
        }
        finally
        {
            CheckingDrops = false;
        }
    }

    [RelayCommand]
    private async Task Logout()
    {
        _auth.Logout();
        await Shell.Current.GoToAsync("..");
    }
}

using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Services;

namespace Hapay.ViewModels;

public partial class ProfileViewModel : ObservableObject
{
    private readonly AuthService _auth;
    private readonly CollectorService _collector;

    public ProfileViewModel(AuthService auth, CollectorService collector)
    {
        _auth = auth;
        _collector = collector;
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

    partial void OnIsCollectingChanged(bool value) => CollectCommand.NotifyCanExecuteChanged();

    public void Refresh()
    {
        OnPropertyChanged(nameof(Email));
        OnPropertyChanged(nameof(Role));
        OnPropertyChanged(nameof(RoleLabel));
        OnPropertyChanged(nameof(IsCollector));
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

    [RelayCommand]
    private async Task Logout()
    {
        _auth.Logout();
        await Shell.Current.GoToAsync("..");
    }
}

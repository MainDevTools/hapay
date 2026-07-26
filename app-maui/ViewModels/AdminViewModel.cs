using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

// Адмін-панель (S15 + S16): акаунти з пошуком/фільтрами (moderator+), зміна ролей
// (лише admin), дії над акаунтом, вхід у метрики й журнал.
//
// Клієнт лише ХОВАЄ недоступне — рішення ухвалює сервер (гейти + захисти). Тому
// відмову сервера показуємо текстом як є, не намагаючись передбачити її локально.
public partial class AdminViewModel : ObservableObject
{
    private readonly ApiService _api;
    private readonly AuthService _auth;

    public ObservableCollection<AdminUser> Users { get; } = new();

    [ObservableProperty] private bool _isLoading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private string? _notice;      // результат останньої дії

    [ObservableProperty] private string _search = "";
    [ObservableProperty] private string _roleFilter = "усі ролі";
    [ObservableProperty] private string _stateFilter = "усі стани";

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PageText))]
    [NotifyPropertyChangedFor(nameof(HasPages))]
    private int _page;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PageText))]
    [NotifyPropertyChangedFor(nameof(HasPages))]
    private int _pages;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(FoundText))]
    private int _total;

    public string FoundText => $"знайдено {Total}";
    public string PageText => $"{Page + 1} / {Math.Max(Pages, 1)}";
    public bool HasPages => Pages > 1;

    /// Зміна ролей і видалення — лише повний адмін (кнопки ховаються у зама).
    public bool CanChangeRoles => _auth.IsAdmin;

    public string[] RoleFilters { get; } =
        { "усі ролі", "юзер", "колектор", "зам адміна", "адмін" };
    public string[] StateFilters { get; } = { "усі стани", "активні", "заблоковані" };

    private static readonly (string Role, string Label)[] RoleChoices =
    {
        ("user", "юзер"), ("collector", "колектор"),
        ("moderator", "зам адміна"), ("admin", "адмін"),
    };

    private CancellationTokenSource? _debounce;

    public AdminViewModel(ApiService api, AuthService auth)
    {
        _api = api;
        _auth = auth;
    }

    public async Task LoadAsync()
    {
        IsLoading = true;
        Error = null;
        try
        {
            var role = RoleChoices.FirstOrDefault(r => r.Label == RoleFilter).Role;
            bool? active = StateFilter == "активні" ? true
                         : StateFilter == "заблоковані" ? false : null;
            var res = await _api.AdminUsersAsync(Search, role, active, Page);
            Users.Clear();
            foreach (var u in res.Users) Users.Add(u);
            Total = res.Total;
            Pages = res.Pages;
            Page = res.Page;
        }
        catch (UnauthorizedException) { Error = "Сесія завершилась — увійди знову."; }
        catch (Exception e) { Error = e.Message; }
        finally { IsLoading = false; }
    }

    // Пошук друкують по літері — не б'ємо сервер на кожне натискання.
    partial void OnSearchChanged(string value)
    {
        _debounce?.Cancel();
        var cts = new CancellationTokenSource();
        _debounce = cts;
        _ = Task.Run(async () =>
        {
            try { await Task.Delay(350, cts.Token); } catch (OperationCanceledException) { return; }
            if (cts.IsCancellationRequested) return;
            MainThread.BeginInvokeOnMainThread(async () => { Page = 0; await LoadAsync(); });
        });
    }

    partial void OnRoleFilterChanged(string value) => _ = ResetAndLoad();
    partial void OnStateFilterChanged(string value) => _ = ResetAndLoad();

    private async Task ResetAndLoad()
    {
        Page = 0;
        await LoadAsync();
    }

    [RelayCommand]
    private Task Refresh() => LoadAsync();

    [RelayCommand]
    private async Task PrevPage()
    {
        if (Page <= 0) return;
        Page--;
        await LoadAsync();
    }

    [RelayCommand]
    private async Task NextPage()
    {
        if (Page + 1 >= Pages) return;
        Page++;
        await LoadAsync();
    }

    [RelayCommand]
    private Task OpenMetrics() => Shell.Current.GoToAsync(nameof(AdminMetricsPage));

    [RelayCommand]
    private Task OpenAudit() => Shell.Current.GoToAsync(nameof(AdminAuditPage));

    /// Змінити роль: вибір зі списку → підтвердження → сервер. Роль — це права,
    /// тож підтверджуємо явно, з іменем акаунта в тексті.
    [RelayCommand]
    private async Task ChangeRole(AdminUser? u)
    {
        if (u is null || Shell.Current is null) return;
        var labels = RoleChoices.Select(r => r.Label).ToArray();
        var picked = await Shell.Current.DisplayActionSheet(
            $"Роль для {u.Email}", "Скасувати", null, labels);
        if (string.IsNullOrEmpty(picked) || picked == "Скасувати") return;
        var role = RoleChoices.FirstOrDefault(r => r.Label == picked).Role;
        if (string.IsNullOrEmpty(role) || role == u.Role) return;

        var ok = await Shell.Current.DisplayAlert("Змінити роль",
            $"{u.Email}: {u.RoleLabel} → {picked}?", "Змінити", "Скасувати");
        if (!ok) return;

        await RunAsync(() => _api.SetUserRoleAsync(u.UserId, role),
                       $"{u.Email}: роль → {picked}");
    }

    /// Бан/розбан із підтвердженням — блокування відрізає людину від акаунта.
    [RelayCommand]
    private async Task ToggleBan(AdminUser? u)
    {
        if (u is null || Shell.Current is null) return;
        var makeActive = !u.IsActive;
        var ok = await Shell.Current.DisplayAlert(
            makeActive ? "Розблокувати" : "Заблокувати",
            makeActive ? $"Повернути доступ {u.Email}?"
                       : $"{u.Email} більше не зможе увійти. Заблокувати?",
            makeActive ? "Розблокувати" : "Заблокувати", "Скасувати");
        if (!ok) return;

        await RunAsync(() => _api.SetUserActiveAsync(u.UserId, makeActive),
                       $"{u.Email}: {(makeActive ? "розблоковано" : "заблоковано")}");
    }

    /// Підтвердити email вручну — підтримка, коли лист не доходить (сервер пише в аудит).
    [RelayCommand]
    private async Task VerifyUser(AdminUser? u)
    {
        if (u is null || Shell.Current is null) return;
        if (!await Shell.Current.DisplayAlert("Підтвердити email",
                $"Підтвердити {u.Email} вручну, без листа?", "Підтвердити", "Скасувати")) return;
        await RunAsync(() => _api.AdminVerifyAsync(u.UserId), $"{u.Email}: email підтверджено");
    }

    [RelayCommand]
    private async Task SendReset(AdminUser? u)
    {
        if (u is null || Shell.Current is null) return;
        if (!await Shell.Current.DisplayAlert("Скидання пароля",
                $"Надіслати {u.Email} код скидання?", "Надіслати", "Скасувати")) return;
        await RunAsync(() => _api.AdminSendResetAsync(u.UserId), $"{u.Email}: код надіслано");
    }

    /// Видалення незворотне — тому подвійне підтвердження, як у веб-панелі.
    [RelayCommand]
    private async Task DeleteUser(AdminUser? u)
    {
        if (u is null || Shell.Current is null) return;
        if (!await Shell.Current.DisplayAlert("Видалити акаунт",
                $"Видалити {u.Email}? Це незворотно.", "Видалити", "Скасувати")) return;
        if (!await Shell.Current.DisplayAlert("Ще раз",
                $"Точно видалити {u.Email} назавжди?", "Видалити", "Скасувати")) return;
        await RunAsync(() => _api.AdminDeleteUserAsync(u.UserId), $"{u.Email}: акаунт видалено");
    }

    /// Спільний хвіст мутацій: виконати → перечитати список (щоб бачити ФАКТИЧНИЙ стан
    /// сервера, а не власну оптимістичну здогадку) → показати підсумок або відмову.
    private async Task RunAsync(Func<Task> action, string successNotice)
    {
        Error = null;
        Notice = null;
        try
        {
            await action();
            Notice = successNotice;
            await LoadAsync();
        }
        catch (UnauthorizedException) { Error = "Сесія завершилась — увійди знову."; }
        catch (Exception e) { Error = e.Message; await LoadAsync(); }
    }
}

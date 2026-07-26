using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

// Адмін-панель (S15): акаунти + метрики (moderator+), зміна ролей (лише admin).
// Клієнт лише ХОВАЄ недоступне — рішення ухвалює сервер (гейти + захисти). Тому
// відмову сервера показуємо текстом як є, не намагаючись передбачити її локально.
public partial class AdminViewModel : ObservableObject
{
    private readonly ApiService _api;
    private readonly AuthService _auth;

    public ObservableCollection<AdminUser> Users { get; } = new();

    [ObservableProperty] private bool _isLoading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private AdminMetrics? _metrics;
    [ObservableProperty] private string? _notice;      // результат останньої дії

    /// Зміна ролей — лише повний адмін (кнопка «Роль» ховається у зама).
    public bool CanChangeRoles => _auth.IsAdmin;

    private static readonly (string Role, string Label)[] RoleChoices =
    {
        ("user", "юзер"), ("collector", "колектор"),
        ("moderator", "зам адміна"), ("admin", "адмін"),
    };

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
            var users = await _api.AdminUsersAsync();
            Users.Clear();
            foreach (var u in users) Users.Add(u);
            Metrics = await _api.AdminMetricsAsync();
        }
        catch (UnauthorizedException) { Error = "Сесія завершилась — увійди знову."; }
        catch (Exception e) { Error = e.Message; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    private Task Refresh() => LoadAsync();

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
        catch (Exception e) { Error = e.Message; }   // 403/400 із detail сервера — текстом
    }
}

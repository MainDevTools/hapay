using CommunityToolkit.Mvvm.ComponentModel;
using Hapay.Models;

namespace Hapay.Services;

/// Стан авторизації + безпечне сховище токена. SecureStorage кладе токен у
/// Android Keystore / iOS Keychain (шифровано ОС) — НЕ в plaintext-налаштування.
public partial class AuthService : ObservableObject
{
    private const string KeyToken = "hapay_token";
    private const string KeyEmail = "hapay_email";
    private const string KeyRole = "hapay_role";

    private readonly ApiService _api;

    [ObservableProperty] private bool _isLoggedIn;
    [ObservableProperty] private string? _email;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsCollector))]   // IsCollector залежить від Role → авто-сповіщення
    private string _role = "user";

    public bool IsCollector => Role is "collector" or "moderator" or "admin";

    public AuthService(ApiService api) => _api = api;

    /// Викликати на старті: підняти збережений токен у память і в ApiService.
    /// SecureStorage.GetAsync на Android може кинути на збої розшифрування (оновлення ОС,
    /// зміна блокування екрана/біометрії, деякі OEM-keystore). Ловимо й трактуємо як
    /// «не залогінений» + чистимо ключі — інакше отруєний ключ = краш-цикл на кожному старті.
    public async Task LoadAsync()
    {
        try
        {
            var token = await SecureStorage.GetAsync(KeyToken);
            if (string.IsNullOrEmpty(token)) return;
            _api.SetToken(token);
            Email = await SecureStorage.GetAsync(KeyEmail);
            Role = await SecureStorage.GetAsync(KeyRole) ?? "user";
            IsLoggedIn = true;
        }
        catch
        {
            // сховище зіпсоване/недоступне → скидаємо до анонімного стану, без крашу
            SecureStorage.RemoveAll();
            _api.SetToken(null);
            IsLoggedIn = false;
            Email = null;
            Role = "user";
        }
    }

    public async Task RegisterAsync(string email, string password)
        => await ApplyAsync(await _api.RegisterAsync(email, password));

    public async Task LoginAsync(string email, string password)
        => await ApplyAsync(await _api.LoginAsync(email, password));

    private async Task ApplyAsync(AuthResult r)
    {
        _api.SetToken(r.Token);
        await SecureStorage.SetAsync(KeyToken, r.Token);
        await SecureStorage.SetAsync(KeyEmail, r.Email);
        await SecureStorage.SetAsync(KeyRole, r.Role);
        Email = r.Email;
        Role = r.Role;   // сповістить і IsCollector (NotifyPropertyChangedFor)
        IsLoggedIn = true;
    }

    /// Звіряє кеш із сервером через /api/me: оновлює email+роль на актуальні (напр. роль
    /// щойно підняли до collector). На 401 (акаунт зник / токен протух) — розлогінює, щоб
    /// застаріла сесія не висіла мовчки. Мережевий збій НЕ розлогінює (лишаємо кеш офлайн).
    /// Повертає true, якщо сесія жива. НЕ кидає — безпечно кликати з async void OnAppearing.
    public async Task<bool> RefreshFromServerAsync()
    {
        if (!IsLoggedIn) return false;
        try
        {
            var me = await _api.MeAsync();
            Email = me.Email;
            Role = me.Role;                                 // сповістить і IsCollector
            await SecureStorage.SetAsync(KeyEmail, me.Email);
            await SecureStorage.SetAsync(KeyRole, me.Role);
            return true;
        }
        catch (UnauthorizedException)
        {
            Logout();                                       // недійсна сесія → чистимо кеш і токен
            return false;
        }
        catch
        {
            return true;                                    // мережа/сховище впали — лишаємо кеш, не викидаємо
        }
    }

    public void Logout()
    {
        SecureStorage.Remove(KeyToken);
        SecureStorage.Remove(KeyEmail);
        SecureStorage.Remove(KeyRole);
        _api.SetToken(null);
        IsLoggedIn = false;
        Email = null;
        Role = "user";   // сповістить і IsCollector (NotifyPropertyChangedFor)
    }
}

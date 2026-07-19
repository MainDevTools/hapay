using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Services;

namespace Hapay.ViewModels;

/// Один екран для входу й реєстрації (перемикач IsRegister).
public partial class LoginViewModel : ObservableObject
{
    private readonly AuthService _auth;

    [ObservableProperty] private string _email = "";
    [ObservableProperty] private string _password = "";
    [ObservableProperty] private bool _isRegister;      // false = вхід, true = реєстрація
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private string? _error;

    public LoginViewModel(AuthService auth) => _auth = auth;

    public string Title => IsRegister ? "Реєстрація" : "Вхід";
    public string SubmitText => IsRegister ? "Зареєструватися" : "Увійти";
    public string ToggleText => IsRegister ? "Уже маєш акаунт? Увійти" : "Немає акаунта? Зареєструватися";

    partial void OnIsRegisterChanged(bool value)
    {
        Error = null;
        OnPropertyChanged(nameof(Title));
        OnPropertyChanged(nameof(SubmitText));
        OnPropertyChanged(nameof(ToggleText));
    }

    [RelayCommand]
    private void Toggle() => IsRegister = !IsRegister;

    [RelayCommand]
    private async Task Submit()
    {
        if (IsBusy) return;
        Error = null;

        if (string.IsNullOrWhiteSpace(Email) || !Email.Contains('@'))
        {
            Error = "Введи коректний email";
            return;
        }
        if (Password.Length < 8)
        {
            Error = "Пароль — щонайменше 8 символів";
            return;
        }

        IsBusy = true;
        try
        {
            if (IsRegister) await _auth.RegisterAsync(Email.Trim(), Password);
            else await _auth.LoginAsync(Email.Trim(), Password);
            Password = "";
            await Shell.Current.GoToAsync("..");   // назад на попередній екран (Home/Profile)
        }
        catch (ApiException e)
        {
            Error = e.Message;                     // осмислена помилка від сервера (email зайнятий тощо)
        }
        catch (Exception)
        {
            Error = "Не вдалося з'єднатися. Перевір інтернет і спробуй ще.";
        }
        finally
        {
            IsBusy = false;
        }
    }
}

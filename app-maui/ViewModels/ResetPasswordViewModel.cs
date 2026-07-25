using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Services;

namespace Hapay.ViewModels;

// «Забув пароль» (S13): двоетапно на одному екрані — email → код на пошту →
// код + новий пароль. Не залогінений флоу (з екрана входу).
public partial class ResetPasswordViewModel : ObservableObject
{
    private readonly ApiService _api;

    [ObservableProperty] private string _email = "";
    [ObservableProperty] private string _code = "";
    [ObservableProperty] private string _newPassword = "";
    [ObservableProperty] private bool _codeSent;       // етап 2 (код+пароль) видно після запиту
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private string? _info;

    public ResetPasswordViewModel(ApiService api) => _api = api;

    [RelayCommand]
    private async Task RequestCode()
    {
        if (IsBusy) return;
        Error = null;
        if (string.IsNullOrWhiteSpace(Email) || !Email.Contains('@'))
        {
            Error = "Введи коректний email";
            return;
        }
        IsBusy = true;
        try
        {
            await _api.RequestResetAsync(Email.Trim().ToLowerInvariant());
            CodeSent = true;
            // сервер не розкриває, чи email існує — тому формулювання умовне
            Info = "Якщо цей email зареєстрований, ми надіслали на нього код. Перевір пошту.";
        }
        catch { Error = "Не вдалося надіслати код. Спробуй пізніше."; }
        finally { IsBusy = false; }
    }

    [RelayCommand]
    private async Task Confirm()
    {
        if (IsBusy) return;
        Error = null;
        if (string.IsNullOrWhiteSpace(Code))
        {
            Error = "Введи код із листа";
            return;
        }
        if (NewPassword.Length < 8)
        {
            Error = "Новий пароль — щонайменше 8 символів";
            return;
        }
        IsBusy = true;
        try
        {
            await _api.ConfirmResetAsync(Email.Trim().ToLowerInvariant(), Code.Trim(), NewPassword);
            await Shell.Current.DisplayAlert("Готово",
                "Пароль змінено. Тепер увійди з новим паролем.", "OK");
            await Shell.Current.GoToAsync("..");        // назад на екран входу
        }
        catch (ApiException e) { Error = e.Message; }   // «код невірний або протермінований»
        catch { Error = "Не вдалося змінити пароль. Спробуй пізніше."; }
        finally { IsBusy = false; }
    }
}

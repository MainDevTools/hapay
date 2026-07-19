using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Services;

namespace Hapay.ViewModels;

public partial class ProfileViewModel : ObservableObject
{
    private readonly AuthService _auth;

    public ProfileViewModel(AuthService auth) => _auth = auth;

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

    public void Refresh()
    {
        OnPropertyChanged(nameof(Email));
        OnPropertyChanged(nameof(Role));
        OnPropertyChanged(nameof(RoleLabel));
        OnPropertyChanged(nameof(IsCollector));
    }

    [RelayCommand]
    private async Task Logout()
    {
        _auth.Logout();
        await Shell.Current.GoToAsync("..");
    }
}

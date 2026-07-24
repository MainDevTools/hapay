using Hapay.ViewModels;

namespace Hapay.Views;

public partial class ProfilePage : ContentPage
{
    private static readonly string[] _themeKeys = { "system", "light", "dark" };
    private readonly ProfileViewModel _vm;
    private bool _themeReady;   // не зберігати тему від програмного виставлення пікера

    public ProfilePage(ProfileViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
        var saved = Preferences.Default.Get(AppShell.ThemeKey, "system");
        ThemePicker.SelectedIndex = Math.Max(0, Array.IndexOf(_themeKeys, saved));
        _themeReady = true;
    }

    private void OnThemeChanged(object? sender, EventArgs e)
    {
        if (!_themeReady || ThemePicker.SelectedIndex < 0) return;
        Preferences.Default.Set(AppShell.ThemeKey, _themeKeys[ThemePicker.SelectedIndex]);
        AppShell.ApplySavedTheme();
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.RefreshAsync();   // звірка з /api/me: актуальні email+роль, авто-logout на 401
    }
}

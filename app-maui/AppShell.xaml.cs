using Hapay.Views;

namespace Hapay;

public partial class AppShell : Shell
{
    public const string ThemeKey = "app_theme";

    /// Тема з Preferences (системна/світла/темна). Викликається на старті (ctor
    /// AppShell — App.xaml.cs живе лише у VS-проєкті, поза синком) і з профілю.
    public static void ApplySavedTheme()
    {
        if (Application.Current is null) return;
        Application.Current.UserAppTheme = Preferences.Default.Get(ThemeKey, "system") switch
        {
            "light" => AppTheme.Light,
            "dark" => AppTheme.Dark,
            _ => AppTheme.Unspecified,
        };
    }

    public AppShell()
    {
        InitializeComponent();
        ApplySavedTheme();
        // маршрути для GoToAsync (CatalogPage — лендинг у ShellContent, тут не реєструємо)
        Routing.RegisterRoute(nameof(HomePage), typeof(HomePage));
        Routing.RegisterRoute(nameof(CategoryPickerPage), typeof(CategoryPickerPage));
        Routing.RegisterRoute(nameof(OnboardingPage), typeof(OnboardingPage));
        Routing.RegisterRoute(nameof(SearchPage), typeof(SearchPage));
        Routing.RegisterRoute(nameof(ResetPasswordPage), typeof(ResetPasswordPage));
        Routing.RegisterRoute(nameof(ComparePage), typeof(ComparePage));
        Routing.RegisterRoute(nameof(AdminPage), typeof(AdminPage));
        Routing.RegisterRoute(nameof(AdminMetricsPage), typeof(AdminMetricsPage));
        Routing.RegisterRoute(nameof(AdminAuditPage), typeof(AdminAuditPage));
        Routing.RegisterRoute(nameof(DetailPage), typeof(DetailPage));
        Routing.RegisterRoute(nameof(DropsPage), typeof(DropsPage));
        Routing.RegisterRoute(nameof(StoresPage), typeof(StoresPage));
        Routing.RegisterRoute(nameof(StorePage), typeof(StorePage));
        Routing.RegisterRoute(nameof(LoginPage), typeof(LoginPage));
        Routing.RegisterRoute(nameof(ProfilePage), typeof(ProfilePage));
        Routing.RegisterRoute(nameof(WatchlistPage), typeof(WatchlistPage));
        // S34: доказовість і канонічна модель більше не вимагають виходу в браузер.
        Routing.RegisterRoute(nameof(HowPage), typeof(HowPage));
        Routing.RegisterRoute(nameof(VerifyPage), typeof(VerifyPage));
        Routing.RegisterRoute(nameof(ModelPage), typeof(ModelPage));
    }
}

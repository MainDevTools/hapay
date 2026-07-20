using Hapay.Views;

namespace Hapay;

public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        // маршрути для GoToAsync (CatalogPage — лендинг у ShellContent, тут не реєструємо)
        Routing.RegisterRoute(nameof(HomePage), typeof(HomePage));
        Routing.RegisterRoute(nameof(DetailPage), typeof(DetailPage));
        Routing.RegisterRoute(nameof(LoginPage), typeof(LoginPage));
        Routing.RegisterRoute(nameof(ProfilePage), typeof(ProfilePage));
        Routing.RegisterRoute(nameof(WatchlistPage), typeof(WatchlistPage));
    }
}

using Hapay.Views;

namespace Hapay;

public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        // маршрути для GoToAsync
        Routing.RegisterRoute(nameof(DetailPage), typeof(DetailPage));
        Routing.RegisterRoute(nameof(LoginPage), typeof(LoginPage));
        Routing.RegisterRoute(nameof(ProfilePage), typeof(ProfilePage));
    }
}

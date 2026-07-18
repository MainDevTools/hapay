using Hapay.Views;

namespace Hapay;

public partial class AppShell : Shell
{
    public AppShell()
    {
        InitializeComponent();
        // маршрут для навігації в картку товару (GoToAsync)
        Routing.RegisterRoute(nameof(DetailPage), typeof(DetailPage));
    }
}

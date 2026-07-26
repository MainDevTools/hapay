using Hapay.ViewModels;

namespace Hapay.Views;

public partial class AdminMetricsPage : ContentPage
{
    private readonly AdminMetricsViewModel _vm;

    public AdminMetricsPage(AdminMetricsViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.LoadAsync();
    }
}

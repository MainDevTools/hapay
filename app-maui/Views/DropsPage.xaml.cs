using Hapay.ViewModels;

namespace Hapay.Views;

public partial class DropsPage : ContentPage
{
    private readonly DropsViewModel _vm;

    public DropsPage(DropsViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        if (_vm.Items.Count == 0) _ = _vm.Load();
    }
}

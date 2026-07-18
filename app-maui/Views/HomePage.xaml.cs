using Hapay.ViewModels;

namespace Hapay.Views;

public partial class HomePage : ContentPage
{
    private readonly HomeViewModel _vm;
    private bool _initialized;

    public HomePage(HomeViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        if (_initialized) return;
        _initialized = true;
        await _vm.InitializeAsync();   // категорії + перше завантаження
    }
}

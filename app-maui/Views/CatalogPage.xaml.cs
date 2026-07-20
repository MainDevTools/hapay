using Hapay.ViewModels;

namespace Hapay.Views;

public partial class CatalogPage : ContentPage
{
    private readonly CatalogViewModel _vm;
    private bool _initialized;

    public CatalogPage(CatalogViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        if (_initialized) return;
        _initialized = true;
        await _vm.InitializeAsync();   // категорії зі знижками → сітка
    }
}

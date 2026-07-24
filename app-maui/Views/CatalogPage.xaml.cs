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
        _vm.RefreshLocal();            // нещодавні/історія запитів — свіжі щоразу
        if (_initialized) return;
        _initialized = true;
        // перший запуск → онбординг (3 слайди, раз); вітрина вантажиться під ним
        if (!Preferences.Default.Get(OnboardingPage.DoneKey, false))
            await Shell.Current.GoToAsync(nameof(OnboardingPage));
        await _vm.InitializeAsync();   // категорії зі знижками → вітрина
    }
}

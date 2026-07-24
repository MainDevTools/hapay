using Hapay.Models;
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

    // Чіп розділу → стрибок сітки до нього. Код-біхайнд свідомо: ScrollTo — операція
    // над View (потрібен сам CollectionView), а не над станом — у VM їй не місце.
    private void OnSectionTapped(object? sender, TappedEventArgs e)
    {
        if ((sender as BindableObject)?.BindingContext is not CategoryGroup g || g.Count == 0)
            return;
        Cv.ScrollTo(g[0], g, ScrollToPosition.Start, animate: true);
    }
}

using Hapay.ViewModels;

namespace Hapay.Views;

public partial class StoresPage : ContentPage
{
    private readonly StoresViewModel _vm;

    public StoresPage(StoresViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    /// Тягнемо на появі, а не в конструкторі: сторінку відкривають із каталогу, і
    /// свіжі числа важливіші за мілісекунду економії.
    protected override void OnAppearing()
    {
        base.OnAppearing();
        if (_vm.Items.Count == 0) _ = _vm.Load();
    }
}

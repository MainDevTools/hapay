using Hapay.ViewModels;

namespace Hapay.Views;

public partial class VerifyPage : ContentPage
{
    private readonly VerifyViewModel _vm;

    public VerifyPage(VerifyViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        _ = _vm.LoadAsync();
    }
}

using Hapay.ViewModels;

namespace Hapay.Views;

public partial class AdminAuditPage : ContentPage
{
    private readonly AdminAuditViewModel _vm;

    public AdminAuditPage(AdminAuditViewModel vm)
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

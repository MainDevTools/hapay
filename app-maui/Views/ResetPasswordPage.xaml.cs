using Hapay.ViewModels;

namespace Hapay.Views;

public partial class ResetPasswordPage : ContentPage
{
    public ResetPasswordPage(ResetPasswordViewModel vm)
    {
        InitializeComponent();
        BindingContext = vm;
    }
}

using Hapay.ViewModels;

namespace Hapay.Views;

public partial class StorePage : ContentPage
{
    public StorePage(StoreViewModel vm)
    {
        InitializeComponent();
        BindingContext = vm;   // дані тягне ApplyQueryAttributes за slug із маршруту
    }
}

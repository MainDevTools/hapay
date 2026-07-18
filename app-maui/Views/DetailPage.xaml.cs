using System.Collections.Specialized;
using Hapay.Drawables;
using Hapay.ViewModels;

namespace Hapay.Views;

public partial class DetailPage : ContentPage
{
    private readonly DetailViewModel _vm;
    private readonly PriceHistoryDrawable _drawable = new();

    public DetailPage(DetailViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
        Chart.Drawable = _drawable;

        // історія вантажиться асинхронно у VM → щойно колекція оновилась, перемальовуємо графік
        _vm.History.CollectionChanged += OnHistoryChanged;
    }

    private void OnHistoryChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        _drawable.Points = _vm.History.ToList();
        Chart.Invalidate();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _vm.History.CollectionChanged -= OnHistoryChanged;   // без витоку підписки
    }
}

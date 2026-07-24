using System.Collections.ObjectModel;
using System.Linq;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

// «Каталог товарів» (E-Katalog-стиль, рішення оператора 2026-07-24): повноекранний
// ДВОРІВНЕВИЙ вибір — список розділів рядками → тап → категорії розділу, з пошуком.
// Відкривається з кнопки категорії у стрічці; вибір повертається назад через ".."
// (query-атрибути) — БЕЗ нового екземпляра HomePage у стеку.
public partial class CategoryPickerViewModel : ObservableObject
{
    private readonly ApiService _api;

    public ObservableCollection<CategoryGroup> Sections { get; } = new();
    public ObservableCollection<Category> Current { get; } = new();   // категорії відкритого розділу
    public ObservableCollection<Category> Found { get; } = new();     // збіги пошуку (плоско)

    [ObservableProperty] private string _searchText = "";
    [ObservableProperty] private string _sectionTitle = "";
    [ObservableProperty] private bool _showSections = true;
    [ObservableProperty] private bool _showCurrent;
    [ObservableProperty] private bool _showFound;
    [ObservableProperty] private string? _errorMessage;

    private readonly List<Category> _all = new();
    private bool _ready;

    public CategoryPickerViewModel(ApiService api) => _api = api;

    public async Task InitializeAsync()
    {
        if (_ready) return;
        try
        {
            var cats = await _api.CategoriesAsync();
            Sections.Clear();
            _all.Clear();
            foreach (var g in cats.Where(c => !string.IsNullOrEmpty(c.Slug))
                                  .GroupBy(c => c.Section))
                Sections.Add(new CategoryGroup(g.Key, g));
            _all.AddRange(cats.Where(c => !string.IsNullOrEmpty(c.Slug)));
            _ready = true;
        }
        catch (Exception e)
        {
            ErrorMessage = e.Message;
        }
    }

    [RelayCommand]
    private void OpenSection(CategoryGroup? g)
    {
        if (g is null) return;
        Current.Clear();
        foreach (var c in g) Current.Add(c);
        SectionTitle = g.Title;
        ShowSections = false;
        ShowCurrent = true;
        ShowFound = false;
    }

    [RelayCommand]
    private void BackToSections()
    {
        SectionTitle = "";
        ShowCurrent = false;
        ShowFound = false;
        ShowSections = true;
    }

    // введення в «Пошук розділу» → плоскі збіги категорій по всьому каталогу
    partial void OnSearchTextChanged(string value)
    {
        var q = value?.Trim();
        if (string.IsNullOrEmpty(q) || q.Length < 2)
        {
            ShowFound = false;
            ShowSections = string.IsNullOrEmpty(SectionTitle);
            ShowCurrent = !ShowSections;
            return;
        }
        Found.Clear();
        foreach (var c in _all.Where(c =>
                     c.Name.Contains(q, StringComparison.CurrentCultureIgnoreCase)
                     || c.Section.Contains(q, StringComparison.CurrentCultureIgnoreCase)).Take(20))
            Found.Add(c);
        ShowFound = true;
        ShowSections = false;
        ShowCurrent = false;
    }

    [RelayCommand]
    private async Task Pick(Category? c)
    {
        if (c is null) return;
        await Shell.Current.GoToAsync("..", new Dictionary<string, object>
        { ["Category"] = c.Slug, ["Title"] = c.Name });
    }

    [RelayCommand]
    private async Task PickAll() => await Shell.Current.GoToAsync("..",
        new Dictionary<string, object> { ["Category"] = "", ["Title"] = "Хапай" });

    [RelayCommand]
    private async Task Close() => await Shell.Current.GoToAsync("..");
}

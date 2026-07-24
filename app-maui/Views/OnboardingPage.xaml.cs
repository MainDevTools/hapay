namespace Hapay.Views;

public record OnboardSlide(string Icon, string Title, string Body);

/// Онбординг — 3 слайди при першому запуску (прапорець у Preferences). Без VM:
/// сторінка суто презентаційна, стану поза собою не має.
public partial class OnboardingPage : ContentPage
{
    public const string DoneKey = "onboarding_v1_done";

    private static readonly IReadOnlyList<OnboardSlide> _slides = new[]
    {
        new OnboardSlide("🛡", "Ми перевіряємо знижки",
            "Хапай щодня зберігає ціни крамниць і звіряє кожну знижку з власною " +
            "історією цін — а не переказує обіцянки магазинів."),
        new OnboardSlide("📉", "Правило 30 днів",
            "За законом чесна «стара ціна» — це найнижча ціна за останні 30 днів. " +
            "Ми рахуємо саме її і позначаємо знижки, де «стара» ціна завищена."),
        new OnboardSlide("🏆", "Наш вибір — прозоро",
            "Найвигідніший спосіб купити ми обираємо відкритою формулою: ціна з " +
            "доставкою, перевірка знижок, самовивіз. Крамниці не платять за позиції."),
    };

    public OnboardingPage()
    {
        InitializeComponent();
        Slides.ItemsSource = _slides;
    }

    private void OnPositionChanged(object? sender, PositionChangedEventArgs e) =>
        NextBtn.Text = e.CurrentPosition >= _slides.Count - 1 ? "Почати" : "Далі";

    private async void OnNextClicked(object? sender, EventArgs e)
    {
        if (Slides.Position < _slides.Count - 1)
        {
            Slides.Position += 1;
            return;
        }
        Preferences.Default.Set(DoneKey, true);
        await Shell.Current.GoToAsync("..");
    }
}

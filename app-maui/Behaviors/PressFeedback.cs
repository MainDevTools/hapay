namespace Hapay.Behaviors;

/// Картка мусить відповісти на дотик.
///
/// Заміряно 2026-07-29: у застосунку не було жодної анімації (0 на 21 XAML). Тап по
/// картці не давав НІЧОГО, доки не відкриється наступний екран, — а мережа між цими
/// двома подіями буває секунду. Ця секунда читається як «не спрацювало», і людина
/// тисне вдруге.
///
/// ⚠ Чому реакція на Tapped, а не на «натиснуто»: TapGestureRecognizer стріляє на
/// ВІДПУСКАННІ, а PointerGestureRecognizer на Android дає дотик не на всіх версіях —
/// будувати на ньому означало б мати ефект «в одних людей є, в інших нема». Тому тут
/// чесний короткий відгук у момент, коли тап уже зарахований: він каже «почули», а не
/// вдає натискання, якого ми не бачимо.
///
/// Власний TapGestureRecognizer, а не перехоплення чужого: розпізнавачі на одному
/// елементі спрацьовують УСІ, тож команда картки лишається недоторканою — поведінку
/// можна зняти, і нічого не зламається.
public sealed class PressFeedback : Behavior<View>
{
    const double Down = 0.97;
    const uint Ms = 90;

    TapGestureRecognizer? _tap;
    // Тримаємо сам елемент, а не дістаємо його з Parent розпізнавача: у клітинках
    // CollectionView дерево перебудовується, і покладатись на батька означало б
    // мати ефект, який іноді просто не спрацьовує.
    View? _view;

    protected override void OnAttachedTo(View v)
    {
        base.OnAttachedTo(v);
        _view = v;
        _tap = new TapGestureRecognizer();
        _tap.Tapped += OnTapped;
        v.GestureRecognizers.Add(_tap);
    }

    protected override void OnDetachingFrom(View v)
    {
        if (_tap is not null)
        {
            _tap.Tapped -= OnTapped;
            v.GestureRecognizers.Remove(_tap);
            _tap = null;
        }
        _view = null;
        base.OnDetachingFrom(v);
    }

    async void OnTapped(object? sender, TappedEventArgs e)
    {
        var v = _view;
        if (v is null) return;
        // Не тримаємо перехід: навігація вже пішла власною командою картки, і
        // затримувати її заради 180 мс краси було б рівно тим гальмом, від якого
        // ця поведінка й рятує.
        // ScaleToAsync, а не ScaleTo: у net10 старий метод позначено obsolete.
        await v.ScaleToAsync(Down, Ms, Easing.CubicOut);
        await v.ScaleToAsync(1.0, Ms, Easing.CubicIn);
    }
}

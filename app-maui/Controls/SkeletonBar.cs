namespace Hapay.Controls;

/// Смужка-заглушка, яка ДИХАЄ, поки чекаємо на дані.
///
/// Заглушки в застосунку були й доти — і це правильно: без них блоки «вистрибували»
/// зі зсувом усього лейауту. Але вони стояли нерухомо, а нерухомий сірий прямокутник
/// не відрізнити від елемента, який просто такий і є. Рух — єдине, що каже «це
/// тимчасово, воно ще вантажиться». Заміряно 2026-07-29: у застосунку не було
/// жодної анімації взагалі (0 викликів FadeTo/ScaleTo/TranslateTo на 21 XAML).
///
/// Чому окремий контрол, а не Behavior: Behaviors не можна задати сеттером у Style
/// (це read-only колекція), тож поведінка все одно чіплялась би до кожної смужки
/// вручну. Контрол-спадкоємець BoxView робить те саме одним словом у розмітці.
///
/// Анімація дешева свідомо: пульс прозорості замість градієнта, що їде. Смужок на
/// екрані буває півтора десятка, і кожен градієнт — це перемальовування шару.
public sealed class SkeletonBar : BoxView
{
    const string AnimationName = "hapay-skeleton";

    // Період підібрано так, щоб пульс читався як «працює», а не як блимання:
    // швидше ≈900 мс починає смикати око, повільніше ≈2 с виглядає як завмерло.
    const uint PeriodMs = 1300;
    const double Dim = 0.45;

    protected override void OnHandlerChanged()
    {
        base.OnHandlerChanged();
        // Handler == null означає, що елемент зняли з дерева (гортання CollectionView
        // переробляє клітинки). Анімацію треба ГАСИТИ: інакше вона житиме на
        // від'єднаному елементі, і кожна прокрутка додаватиме ще один таймер.
        if (Handler is null) { this.AbortAnimation(AnimationName); return; }
        Start();
    }

    void Start()
    {
        var a = new Animation(v => Opacity = v, 1.0, Dim, Easing.SinInOut);
        var back = new Animation(v => Opacity = v, Dim, 1.0, Easing.SinInOut);
        var seq = new Animation();
        seq.Add(0.0, 0.5, a);
        seq.Add(0.5, 1.0, back);
        seq.Commit(this, AnimationName, 16, PeriodMs, repeat: () => true);
    }
}

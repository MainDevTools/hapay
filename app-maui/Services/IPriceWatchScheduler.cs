namespace Hapay.Services;

/// Періодична перевірка «чи подешевшало щось із відстежуваного» + ЛОКАЛЬНЕ сповіщення.
///
/// Свідомо БЕЗ push-сервісів (FCM тощо): §7.7 забороняє телеметрію, а push гнав би
/// перелік товарів користувача через чужий сервер і вимагав би окремої згоди в
/// політиці конфіденційності. Телефон і так прокидається за розкладом — цього досить,
/// бо зниження ціни не потребує доставки за секунди.
public interface IPriceWatchScheduler
{
    bool IsSupported { get; }

    /// Увімкнути періодичну перевірку (перезаписує розклад).
    void Enable();

    /// Вимкнути.
    void Disable();

    /// Відновити після перезапуску застосунку, якщо є за чим стежити.
    void EnsureIfEnabled();
}

/// Заглушка для платформ без фонових задач (Windows-дебаг тощо).
public class NoopPriceWatchScheduler : IPriceWatchScheduler
{
    public bool IsSupported => false;
    public void Enable() { }
    public void Disable() { }
    public void EnsureIfEnabled() { }
}

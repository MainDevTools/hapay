namespace Hapay.Services;

/// Планувальник фонового збору (T16 крок 2). Android — WorkManager (періодично ~15 хв,
/// Wi-Fi + зарядка); інші платформи — no-op (iOS свідомо пізніше: фонові задачі там
/// без гарантій розкладу).
public interface ICollectScheduler
{
    bool IsSupported { get; }

    /// Увімкнути періодичний фоновий збір (перезаписує розклад).
    void Enable();

    /// Вимкнути фоновий збір.
    void Disable();

    /// На старті застосунку: відновити розклад, якщо користувач умикав (не скидає період).
    void EnsureIfEnabled();
}

/// Заглушка для платформ без фонового збору.
public class NoopCollectScheduler : ICollectScheduler
{
    public bool IsSupported => false;
    public void Enable() { }
    public void Disable() { }
    public void EnsureIfEnabled() { }
}

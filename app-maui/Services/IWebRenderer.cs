namespace Hapay.Services;

/// Рендер SPA-сторінки як браузер (WebView) → готовий HTML із цінами (T-WebView).
/// SSR-крамниці збираються простим fetch; ці — лише через рендер. Android — справжній
/// офскрін-WebView; інші платформи — no-op (null → колектор пропустить render-задачу).
public interface IWebRenderer
{
    bool IsSupported { get; }

    /// Завантажити URL, дочекатись JS-рендеру, віддати document HTML (або null на збій/таймаут).
    Task<string?> RenderHtmlAsync(string url, CancellationToken ct = default);
}

public class NoopWebRenderer : IWebRenderer
{
    public bool IsSupported => false;
    public Task<string?> RenderHtmlAsync(string url, CancellationToken ct = default) =>
        Task.FromResult<string?>(null);
}

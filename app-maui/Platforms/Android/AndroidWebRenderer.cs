using System.Text.Json;
using Android.Webkit;
using AWebView = Android.Webkit.WebView;

namespace Hapay.Services;

/// Android офскрін-WebView: рендерить SPA-крамницю як браузер і віддає готовий HTML
/// (T-WebView). WebView живе на UI-потоці, не в дереві вью (Layout у віртуальний
/// вьюпорт, щоб respondsive/lazy-контент відрендерився). Після OnPageFinished чекаємо
/// SETTLE (JS домальовує ціни), тоді витягуємо document.documentElement.outerHTML.
public class AndroidWebRenderer : IWebRenderer
{
    private const int SettleMs = 4000;      // пауза після завантаження — JS домальовує ціни
    private const int TimeoutMs = 35000;    // страховка від зависання сторінки

    public bool IsSupported => true;

    public async Task<string?> RenderHtmlAsync(string url, CancellationToken ct = default)
    {
        var tcs = new TaskCompletionSource<string?>();
        AWebView? web = null;

        await MainThread.InvokeOnMainThreadAsync(() =>
        {
            var ctx = Platform.CurrentActivity ?? global::Android.App.Application.Context!;
            web = new AWebView(ctx);
            var s = web.Settings;
            s.JavaScriptEnabled = true;
            s.DomStorageEnabled = true;
            s.LoadsImagesAutomatically = false;   // фото не тягнемо (вказівники беремо з розмітки) — економія
            s.BlockNetworkImage = true;
            s.UserAgentString = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              + "(KHTML, like Gecko) Chrome/124.0 Safari/537.36";
            web.SetWebViewClient(new RenderClient(tcs));
            web.Layout(0, 0, 1080, 3200);         // віртуальний вьюпорт (не в дереві вью)
            web.LoadUrl(url);
        });

        using var timeoutReg = ct.Register(() => tcs.TrySetResult(null));
        var timeout = Task.Delay(TimeoutMs, CancellationToken.None);
        var finished = await Task.WhenAny(tcs.Task, timeout);
        var html = finished == tcs.Task ? await tcs.Task : null;

        // прибрати WebView (на UI-потоці) — не тримати память/мережу
        if (web is not null)
            await MainThread.InvokeOnMainThreadAsync(() =>
            {
                try { web.StopLoading(); web.Destroy(); } catch { /* best-effort */ }
            });
        return string.IsNullOrWhiteSpace(html) ? null : html;
    }

    private sealed class RenderClient : WebViewClient
    {
        private readonly TaskCompletionSource<string?> _tcs;
        private bool _extracted;
        public RenderClient(TaskCompletionSource<string?> tcs) => _tcs = tcs;

        public override async void OnPageFinished(AWebView? view, string? url)
        {
            base.OnPageFinished(view, url);
            if (_extracted || view is null) return;
            _extracted = true;
            try
            {
                await Task.Delay(SettleMs);       // дати JS домалювати ціни
                view.EvaluateJavascript("document.documentElement.outerHTML", new Extract(_tcs));
            }
            catch { _tcs.TrySetResult(null); }
        }

        public override void OnReceivedError(AWebView? view, IWebResourceRequest? request,
                                             WebResourceError? error)
        {
            // помилка головного документа → віддаємо null (колектор зробить collect/fail)
            if (request?.IsForMainFrame == true) _tcs.TrySetResult(null);
        }
    }

    /// Колбек EvaluateJavascript: рядок приходить JSON-екранованим → розекрануємо.
    private sealed class Extract : Java.Lang.Object, IValueCallback
    {
        private readonly TaskCompletionSource<string?> _tcs;
        public Extract(TaskCompletionSource<string?> tcs) => _tcs = tcs;

        public void OnReceiveValue(Java.Lang.Object? value)
        {
            var raw = value?.ToString();
            if (string.IsNullOrEmpty(raw) || raw == "null") { _tcs.TrySetResult(null); return; }
            try { _tcs.TrySetResult(JsonSerializer.Deserialize<string>(raw)); }
            catch { _tcs.TrySetResult(raw); }     // якщо вже не в лапках — беремо як є
        }
    }
}

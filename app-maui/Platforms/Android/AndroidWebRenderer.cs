using System.Text.Json;
using Android.Webkit;
using AWebView = Android.Webkit.WebView;

namespace Hapay.Services;

/// Android офскрін-WebView: рендерить SPA-крамницю як браузер і віддає готовий HTML
/// (T-WebView). WebView живе на UI-потоці, не в дереві вью (Layout у віртуальний
/// вьюпорт, щоб responsive/lazy-контент відрендерився).
///
/// Після OnPageFinished ПРОКРУЧУЄМО сторінку, доки розмір DOM не перестане рости
/// (розвідка 2026-07-20): багато крамниць домальовують ціни лише коли картка потрапляє
/// у вьюпорт. Eldorado без скролу віддає 32 товари БЕЗ жодної ціни, а після прокрутки —
/// 30 цінників; Brain на нескінченному скролі так само віддає лише перший екран.
/// Стара логіка «почекати 4 с і зняти» цього не ловила — звідси й давні «render дав 0».
public class AndroidWebRenderer : IWebRenderer
{
    private const int SettleMs = 2500;      // пауза після завантаження — перший рендер
    private const int ScrollPauseMs = 1200; // пауза між прокрутками — дати дозавантажитись
    private const int MaxScrollSteps = 12;  // стеля прокруток (страховка від безкінечної стрічки)
    private const int StableRounds = 2;     // стільки разів поспіль DOM не змінився → досить
    private const int TimeoutMs = 60000;    // страховка від зависання (зросла: скрол довший)

    public bool IsSupported => true;

    public async Task<string?> RenderHtmlAsync(string url, CancellationToken ct = default)
    {
        var loaded = new TaskCompletionSource<bool>();
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
            web.SetWebViewClient(new RenderClient(loaded));
            web.Layout(0, 0, 1080, 3200);         // віртуальний вьюпорт (не в дереві вью)
            web.LoadUrl(url);
        });

        using var timeoutReg = ct.Register(() => loaded.TrySetResult(false));
        var finished = await Task.WhenAny(loaded.Task, Task.Delay(TimeoutMs, CancellationToken.None));
        var ok = finished == loaded.Task && loaded.Task.Result;

        string? html = null;
        if (ok && web is not null)
        {
            try
            {
                await Task.Delay(SettleMs);
                html = await ScrollAndExtractAsync(web, ct);
            }
            catch { html = null; }
        }

        // прибрати WebView (на UI-потоці) — не тримати память/мережу
        if (web is not null)
            await MainThread.InvokeOnMainThreadAsync(() =>
            {
                try { web.StopLoading(); web.Destroy(); } catch { /* best-effort */ }
            });
        return string.IsNullOrWhiteSpace(html) ? null : html;
    }

    /// Прокрутка до стабілізації DOM, тоді знімок. Розмір outerHTML — найпростіший
    /// надійний сигнал «дозавантажилось»: він росте, поки додаються картки й ціни.
    private static async Task<string?> ScrollAndExtractAsync(AWebView web, CancellationToken ct)
    {
        long prev = -1;
        int stable = 0;
        for (int step = 0; step < MaxScrollSteps && stable < StableRounds; step++)
        {
            if (ct.IsCancellationRequested) break;
            // прокручуємо на ~екран і будимо lazy-слухачів, які чекають на подію scroll
            var sizeText = await EvalAsync(web,
                "(function(){window.scrollBy(0, Math.round(window.innerHeight*0.9));" +
                "window.dispatchEvent(new Event('scroll'));" +
                "return String(document.documentElement.outerHTML.length);})()");

            if (!long.TryParse(sizeText, out var size)) break;   // сторінка не відповідає — знімаємо як є
            stable = size == prev ? stable + 1 : 0;
            prev = size;
            await Task.Delay(ScrollPauseMs);
        }
        return await EvalAsync(web, "document.documentElement.outerHTML");
    }

    /// EvaluateJavascript у вигляді await-абельного виклику (сам API — колбечний).
    /// Виконуємо на UI-потоці: WebView з інших потоків чіпати не можна.
    private static async Task<string?> EvalAsync(AWebView web, string js)
    {
        var tcs = new TaskCompletionSource<string?>();
        await MainThread.InvokeOnMainThreadAsync(() =>
        {
            try { web.EvaluateJavascript(js, new Extract(tcs)); }
            catch { tcs.TrySetResult(null); }
        });
        return await tcs.Task;
    }

    private sealed class RenderClient : WebViewClient
    {
        private readonly TaskCompletionSource<bool> _loaded;
        private bool _done;
        public RenderClient(TaskCompletionSource<bool> loaded) => _loaded = loaded;

        public override void OnPageFinished(AWebView? view, string? url)
        {
            base.OnPageFinished(view, url);
            if (_done || view is null) return;
            _done = true;
            _loaded.TrySetResult(true);
        }

        public override void OnReceivedError(AWebView? view, IWebResourceRequest? request,
                                             WebResourceError? error)
        {
            // помилка головного документа → віддаємо null (колектор зробить collect/fail)
            if (request?.IsForMainFrame == true) _loaded.TrySetResult(false);
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

using Android.App;
using Android.Content;
using Android.Content.PM;
using Android.OS;

namespace Hapay;

/// <summary>
/// Точка входу Android + обробка ГЛИБОКИХ ПОСИЛАНЬ (App Links).
///
/// ⚠ Цей файл живе в репо саме заради IntentFilter. Раніше він був лише у VS-проєкті
/// (тобто поза історією), а маніфест правити не можна з тієї ж причини: `sync-maui.ps1`
/// копіює з репо в проєкт, і правка, зроблена «на місці», загубиться при наступній
/// синхронізації. Тому фільтр оголошено атрибутом — так само, як дозвіл на сповіщення
/// в AndroidPriceWatch.
///
/// ⚠ AutoVerify сам по собі НЕ вмикає відкриття в застосунку: Android перевіряє
/// `https://hapay.today/.well-known/assetlinks.json` і шукає там відбиток нашого
/// підпису. Поки на сервері не задано `ANDROID_CERT_SHA256`, той файл віддає 404,
/// перевірка не проходить, і Android 12+ мовчки веде посилання в браузер. Відбиток
/// може дати лише власник ключа підпису — 🧭 оператор.
/// </summary>
[Activity(Theme = "@style/Maui.SplashTheme", MainLauncher = true, LaunchMode = LaunchMode.SingleTop,
          ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation
                               | ConfigChanges.UiMode | ConfigChanges.ScreenLayout
                               | ConfigChanges.SmallestScreenSize | ConfigChanges.Density)]
[IntentFilter(new[] { Intent.ActionView },
              Categories = new[] { Intent.CategoryDefault, Intent.CategoryBrowsable },
              DataScheme = "https", DataHost = "hapay.today", DataPathPrefix = "/product/",
              AutoVerify = true)]
public class MainActivity : MauiAppCompatActivity
{
    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        HandleLink(Intent);          // застосунок був закритий — посилання прийшло разом зі стартом
    }

    /// LaunchMode.SingleTop: якщо застосунок уже відкритий, нового Activity не буде —
    /// посилання приходить сюди. Без цього другий перехід за посиланням не спрацював би.
    protected override void OnNewIntent(Intent? intent)
    {
        base.OnNewIntent(intent);
        Intent = intent;
        HandleLink(intent);
    }

    private static void HandleLink(Intent? intent)
    {
        var path = intent?.Data?.Path;                       // «/product/3307»
        if (string.IsNullOrEmpty(path)) return;
        var tail = path.TrimEnd('/');
        var slash = tail.LastIndexOf('/');
        if (slash < 0 || !int.TryParse(tail[(slash + 1)..], out var id) || id <= 0) return;

        // На ХОЛОДНОМУ старті Shell ще не існує в момент, коли прилітає посилання, —
        // тому чекаємо його появи, а не перевіряємо один раз. Без цього перше
        // посилання (найважливіше: людина прийшла з чату) мовчки нікуди б не вело.
        MainThread.BeginInvokeOnMainThread(async () =>
        {
            try
            {
                for (var i = 0; i < 50 && Shell.Current is null; i++)
                    await Task.Delay(100);
                if (Shell.Current is null) return;
                await Shell.Current.GoToAsync($"{nameof(Views.DetailPage)}?id={id}");
            }
            catch (Exception e)
            {
                System.Diagnostics.Debug.WriteLine($"deep link {path}: {e.Message}");
            }
        });
    }
}

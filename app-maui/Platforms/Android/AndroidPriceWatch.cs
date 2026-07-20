using Android.App;
using Android.Content;
using Android.OS;
using AndroidX.Core.App;
using AndroidX.Work;
using Microsoft.Extensions.DependencyInjection;

// Android 13+ вимагає рантайм-дозвіл на сповіщення. Оголошуємо його атрибутом збірки,
// а не правкою AndroidManifest.xml: маніфест лежить у VS-проєкті поза репо, і правка
// в ньому загубилась би при наступній синхронізації.
[assembly: UsesPermission(global::Android.Manifest.Permission.PostNotifications)]

namespace Hapay.Services;

/// Періодична перевірка зниження цін + ЛОКАЛЬНЕ сповіщення (без FCM — див.
/// IPriceWatchScheduler). Раз на годину: зниження ціни не терміновіше за це, а частіше
/// будити телефон заради одного маленького запиту нема сенсу.
public class AndroidPriceWatchScheduler : IPriceWatchScheduler
{
    private const string WorkName = "hapay-pricewatch";

    public bool IsSupported => true;

    public void Enable() => Schedule(ExistingPeriodicWorkPolicy.Update!);

    public void Disable() =>
        WorkManager.GetInstance(global::Android.App.Application.Context!)
                   .CancelUniqueWork(WorkName);

    // Keep — не скидати період на кожному старті
    public void EnsureIfEnabled() => Schedule(ExistingPeriodicWorkPolicy.Keep!);

    private static void Schedule(ExistingPeriodicWorkPolicy policy)
    {
        // на відміну від збору — БЕЗ вимоги зарядки й Wi-Fi: це один крихітний запит,
        // і сповіщення марне, якщо приходить лише коли телефон на зарядці вдома
        var constraints = new Constraints.Builder()
            .SetRequiredNetworkType(NetworkType.Connected!)
            .Build();
        var request = new PeriodicWorkRequest.Builder(
                Java.Lang.Class.FromType(typeof(PriceWatchWorker)),
                1, Java.Util.Concurrent.TimeUnit.Hours!)
            .SetConstraints(constraints)
            .Build();
        WorkManager.GetInstance(global::Android.App.Application.Context!)
                   .EnqueueUniquePeriodicWork(WorkName, policy, request);
    }
}

/// Робітник: питає сервер про зниження, показує сповіщення, підтверджує показ.
/// Ack робимо ЛИШЕ після успішного показу — інакше зниження «зникло б» непоміченим.
public class PriceWatchWorker : Worker
{
    public PriceWatchWorker(Context context, WorkerParameters workerParams)
        : base(context, workerParams) { }

    public override Result DoWork()
    {
        try
        {
            var services = IPlatformApplication.Current?.Services;
            var auth = services?.GetService<AuthService>();
            var api = services?.GetService<ApiService>();
            if (auth is null || api is null)
                return Result.InvokeRetry()!;

            Task.Run(async () =>
            {
                await auth.LoadAsync();               // токен із SecureStorage (без UI)
                if (!auth.IsLoggedIn) return;         // нема акаунта — нема за чим стежити

                var drops = await api.DropsAsync();
                if (drops.Count == 0) return;

                PriceDropNotifier.Show(ApplicationContext!, drops);
                await api.AckDropsAsync(drops.Select(d => d.WatchlistId));
            }).GetAwaiter().GetResult();

            return Result.InvokeSuccess()!;
        }
        catch
        {
            return Result.InvokeRetry()!;             // WorkManager сам зробить бекоф
        }
    }
}

/// Локальне сповіщення про зниження. Текст будуємо лише з ВИМІРЯНОГО (§7.5):
/// назва товару, нова ціна і різниця, яку порахував сервер.
public static class PriceDropNotifier
{
    private const string ChannelId = "hapay-price-drops";
    private const int NotificationId = 1001;

    public static void Show(Context ctx, IReadOnlyList<Models.PriceDrop> drops)
    {
        EnsureChannel(ctx);

        var first = drops[0];
        var title = drops.Count == 1
            ? "Ціна впала"
            : $"Ціни впали — {drops.Count} товари";
        var text = drops.Count == 1
            ? $"{first.Title}: {first.CurrentGrn} (−{first.DropGrn})"
            : $"{first.Title}: −{first.DropGrn} і ще {drops.Count - 1}";

        // тап по сповіщенню → відкрити застосунок (там «Мої відстеження» у профілі)
        var intent = ctx.PackageManager?.GetLaunchIntentForPackage(ctx.PackageName!);
        intent?.SetFlags(ActivityFlags.NewTask | ActivityFlags.ClearTop);
        var pending = PendingIntent.GetActivity(
            ctx, 0, intent, PendingIntentFlags.Immutable | PendingIntentFlags.UpdateCurrent);

        var n = new NotificationCompat.Builder(ctx, ChannelId)
            .SetContentTitle(title)!
            .SetContentText(text)!
            .SetStyle(new NotificationCompat.BigTextStyle().BigText(text!))!
            .SetSmallIcon(global::Android.Resource.Drawable.IcDialogInfo)!
            .SetAutoCancel(true)!
            .SetContentIntent(pending)!
            .Build();

        try { NotificationManagerCompat.From(ctx).Notify(NotificationId, n); }
        catch (Java.Lang.SecurityException) { /* користувач не дав дозвіл — мовчимо */ }
    }

    private static void EnsureChannel(Context ctx)
    {
        if (Build.VERSION.SdkInt < BuildVersionCodes.O) return;
        var mgr = (NotificationManager?)ctx.GetSystemService(Context.NotificationService);
        if (mgr?.GetNotificationChannel(ChannelId) is not null) return;
        var ch = new NotificationChannel(ChannelId, "Зниження цін", NotificationImportance.Default)
        {
            Description = "Сповіщення, коли дешевшає товар із твоїх відстежень",
        };
        mgr?.CreateNotificationChannel(ch);
    }
}

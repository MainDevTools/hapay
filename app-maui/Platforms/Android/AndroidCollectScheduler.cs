using Android.Content;
using AndroidX.Work;
using Microsoft.Extensions.DependencyInjection;

namespace Hapay.Services;

/// Android-планувальник фонового збору (T16 крок 2): WorkManager, PeriodicWorkRequest
/// кожні 15 хв (мінімум ОС і водночас наш крок черги) З КОНСТРЕЙНТАМИ Wi-Fi (Unmetered)
/// + зарядка — дефолти оператора. Без foreground service і постійного сповіщення:
/// прохід короткий (~3 сторінки), WorkManager для цього і створений. Працює навіть
/// коли застосунок закритий (ОС підніме процес → MauiApplication збудує DI).
public class AndroidCollectScheduler : ICollectScheduler
{
    private const string WorkName = "hapay-collect";

    public bool IsSupported => true;

    public void Enable() => Schedule(ExistingPeriodicWorkPolicy.Update!);

    public void Disable() =>
        WorkManager.GetInstance(global::Android.App.Application.Context!)
                   .CancelUniqueWork(WorkName);

    public void EnsureIfEnabled()
    {
        // Keep — не скидати період на кожному старті застосунку
        if (CollectPrefs.AutoEnabled) Schedule(ExistingPeriodicWorkPolicy.Keep!);
    }

    private static void Schedule(ExistingPeriodicWorkPolicy policy)
    {
        var constraints = new Constraints.Builder()
            .SetRequiredNetworkType(NetworkType.Unmetered!)   // лише Wi-Fi — не палимо мобільний трафік
            .SetRequiresCharging(true)                        // лише на зарядці — не палимо батарею
            .Build();
        var request = new PeriodicWorkRequest.Builder(
                Java.Lang.Class.FromType(typeof(CollectWorker)),
                15, Java.Util.Concurrent.TimeUnit.Minutes!)
            .SetConstraints(constraints)
            .Build();
        WorkManager.GetInstance(global::Android.App.Application.Context!)
                   .EnqueueUniquePeriodicWork(WorkName, policy, request);
    }
}

/// Робітник WorkManager: один прохід по черзі-оренді. Швидкий (≤3 сторінки),
/// вкладається у вікно виконання; збій → Retry (WorkManager сам зробить бекоф).
public class CollectWorker : Worker
{
    public CollectWorker(Context context, WorkerParameters workerParams)
        : base(context, workerParams) { }

    public override Result DoWork()
    {
        try
        {
            var services = IPlatformApplication.Current?.Services;
            var auth = services?.GetService<AuthService>();
            var collector = services?.GetService<CollectorService>();
            if (auth is null || collector is null)
                return Result.InvokeRetry()!;

            Task.Run(async () =>
            {
                await auth.LoadAsync();                      // токен із SecureStorage (без UI)
                if (!auth.IsLoggedIn || !auth.IsCollector)
                    return;                                  // не колектор → тихо нічого не робимо
                await collector.RunQueuePassAsync();
            }).GetAwaiter().GetResult();

            return Result.InvokeSuccess()!;
        }
        catch
        {
            return Result.InvokeRetry()!;
        }
    }
}

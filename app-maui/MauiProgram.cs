using Microsoft.Extensions.Logging;
using Hapay.Services;
using Hapay.ViewModels;
using Hapay.Views;

namespace Hapay;

public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        var builder = MauiApp.CreateBuilder();
        builder
            .UseMauiApp<App>()
            .ConfigureFonts(fonts =>
            {
                fonts.AddFont("OpenSans-Regular.ttf", "OpenSansRegular");
                fonts.AddFont("OpenSans-Semibold.ttf", "OpenSansSemibold");
            });

        // DI: сервіси — по одному на застосунок (Auth тримає стан токена); VM/сторінки — нові.
        builder.Services.AddSingleton<ApiService>();
        builder.Services.AddSingleton<AuthService>();
        builder.Services.AddSingleton<CollectorService>();
#if ANDROID
        builder.Services.AddSingleton<ICollectScheduler, AndroidCollectScheduler>();
        builder.Services.AddSingleton<IWebRenderer, AndroidWebRenderer>();
#else
        builder.Services.AddSingleton<ICollectScheduler, NoopCollectScheduler>();
        builder.Services.AddSingleton<IWebRenderer, NoopWebRenderer>();
#endif
        builder.Services.AddTransient<HomeViewModel>();
        builder.Services.AddTransient<HomePage>();
        builder.Services.AddTransient<DetailViewModel>();
        builder.Services.AddTransient<DetailPage>();
        builder.Services.AddTransient<LoginViewModel>();
        builder.Services.AddTransient<LoginPage>();
        builder.Services.AddTransient<ProfileViewModel>();
        builder.Services.AddTransient<ProfilePage>();

#if DEBUG
        builder.Logging.AddDebug();
#endif
        return builder.Build();
    }
}

using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

[assembly: System.Reflection.AssemblyTitle("Sports Cave OS Desktop")]
[assembly: System.Reflection.AssemblyDescription("Persistent native Windows host for Sports Cave OS")]
[assembly: System.Reflection.AssemblyProduct("Sports Cave OS Desktop")]
[assembly: System.Reflection.AssemblyCompany("Sports Cave")]
[assembly: System.Reflection.AssemblyVersion("11.0.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("11.0.0.0")]

internal static class Program
{
    internal const int HelperVersion = 11;
    internal const string FilesAppUserModelId = "SportsCave.Files.Desktop";
    private const string MutexName = @"Local\SportsCaveOSDesktop-v9";
    private const string ShowEventName = @"Local\SportsCaveOSDesktop-Show-v9";
    private const string FilesEventName = @"Local\SportsCaveOSDesktop-Files-v9";

    private static string InstanceName(string baseName)
    {
        string suffix = Convert.ToString(
            Environment.GetEnvironmentVariable("SPORTS_CAVE_DESKTOP_INSTANCE"));
        if (String.IsNullOrWhiteSpace(suffix))
        {
            return baseName;
        }

        var safeSuffix = new string(suffix.Where(
            character => Char.IsLetterOrDigit(character) || character == '-').ToArray());
        return String.IsNullOrWhiteSpace(safeSuffix)
            ? baseName
            : baseName + "-" + safeSuffix;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string protocol = args.Length == 1 ? args[0] : "";
            bool show = args.Length == 1 && args[0] == "--app";
            bool openFiles = false;
            if (Uri.IsWellFormedUriString(protocol, UriKind.Absolute))
            {
                Uri request = new Uri(protocol);
                if (request.Scheme == "sports-cave-files" && request.Host == "launch")
                {
                    var launchConfig = DesktopConfig.Load();
                    string launchUrl = BrowserFileLaunch.Resolve(request, launchConfig);
                    var launchApp = new System.Windows.Application();
                    var launchWindow = new DesktopWindow(launchConfig, launchUrl, false);
                    launchWindow.Title = "Sports Cave — Open file";
                    launchWindow.Width = 580; launchWindow.Height = 360;
                    launchWindow.MinWidth = 420; launchWindow.MinHeight = 300;
                    launchApp.Run(launchWindow);
                    return 0;
                }
                if ((request.Scheme == "sports-cave-files" || request.Scheme == "sports-cave-photoshop")
                    && request.Host == "open")
                {
                    return ForwardOpenProtocol(protocol);
                }
                if (request.Scheme == "sports-cave-files" && request.Host == "app"
                    && String.IsNullOrEmpty(request.Query))
                {
                    show = true;
                    openFiles = true;
                }
                else
                {
                    return 1;
                }
            }
            else if (args.Length > 1 || (args.Length == 1 && args[0] != "--background" && args[0] != "--app"))
            {
                return 1;
            }

            bool ownsMutex;
            using (var mutex = new Mutex(true, InstanceName(MutexName), out ownsMutex))
            {
                if (!ownsMutex)
                {
                    if (openFiles)
                    {
                        using (var signal = EventWaitHandle.OpenExisting(InstanceName(FilesEventName)))
                        {
                            signal.Set();
                        }
                    }
                    else if (show)
                    {
                        using (var signal = EventWaitHandle.OpenExisting(InstanceName(ShowEventName)))
                        {
                            signal.Set();
                        }
                    }
                    return 0;
                }

                var config = DesktopConfig.Load();
                NativeMethods.SetCurrentProcessExplicitAppUserModelID(FilesAppUserModelId);
                var application = new System.Windows.Application();
                application.ShutdownMode = ShutdownMode.OnExplicitShutdown;
                var window = new DesktopWindow(config);
                using (var showEvent = new EventWaitHandle(
                    false, EventResetMode.AutoReset, InstanceName(ShowEventName)))
                using (var filesEvent = new EventWaitHandle(
                    false, EventResetMode.AutoReset, InstanceName(FilesEventName)))
                {
                    var waiter = new Thread(delegate()
                    {
                        while (showEvent.WaitOne())
                        {
                            window.Dispatcher.BeginInvoke(new Action(window.ShowAndFocus));
                        }
                    });
                    waiter.IsBackground = true;
                    waiter.Name = "SportsCaveDesktopShow";
                    waiter.Start();
                    var filesWaiter = new Thread(delegate()
                    {
                        while (filesEvent.WaitOne())
                        {
                            window.Dispatcher.BeginInvoke(new Action(window.NavigateToFiles));
                        }
                    });
                    filesWaiter.IsBackground = true;
                    filesWaiter.Name = "SportsCaveDesktopFiles";
                    filesWaiter.Start();
                    if (show)
                    {
                        window.Show();
                    }
                    if (openFiles)
                    {
                        window.NavigateToFiles();
                    }
                    application.Run();
                }
            }
            return 0;
        }
        catch (Exception error)
        {
            DesktopLog.Write("startup", "failed", error.GetType().Name, 0);
            return 1;
        }
    }

    private static int ForwardOpenProtocol(string protocolUri)
    {
        string helperPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "SportsCaveFilesHelper.ps1");
        string powershellPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.System),
            "WindowsPowerShell", "v1.0", "powershell.exe");
        if (!File.Exists(helperPath) || !File.Exists(powershellPath))
        {
            return 1;
        }
        var start = new ProcessStartInfo();
        start.FileName = powershellPath;
        start.Arguments = "-WindowStyle Hidden -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "
            + QuoteArgument(helperPath) + " " + QuoteArgument(protocolUri);
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        start.WindowStyle = ProcessWindowStyle.Hidden;
        Process.Start(start);
        return 0;
    }

    internal static string QuoteArgument(string value)
    {
        if (value.IndexOfAny(new[] { '\0', '\r', '\n' }) >= 0)
        {
            throw new ArgumentException("Invalid command argument.");
        }
        var quoted = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char character in value)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }
            if (character == '"')
            {
                quoted.Append('\\', (backslashes * 2) + 1);
                quoted.Append('"');
                backslashes = 0;
                continue;
            }
            quoted.Append('\\', backslashes);
            quoted.Append(character);
            backslashes = 0;
        }
        quoted.Append('\\', backslashes * 2);
        quoted.Append('"');
        return quoted.ToString();
    }
}

internal sealed class DesktopConfig
{
    internal string AppUrl;
    internal string RootPath;
    internal HashSet<string> AllowedOrigins;

    internal static DesktopConfig Load()
    {
        string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "config.json");
        var origins = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        string appUrl = "https://sports-cave-image-factory.onrender.com/files-window";
        string rootPath = "";
        if (File.Exists(path))
        {
            var raw = new JavaScriptSerializer().DeserializeObject(File.ReadAllText(path))
                as Dictionary<string, object>;
            if (raw != null)
            {
                if (raw.ContainsKey("AppUrl"))
                {
                    appUrl = Convert.ToString(raw["AppUrl"]);
                }
                if (raw.ContainsKey("RootPath"))
                {
                    rootPath = Convert.ToString(raw["RootPath"]).Trim();
                }
                if (raw.ContainsKey("AllowedOrigins"))
                {
                    var values = raw["AllowedOrigins"] as IEnumerable;
                    if (values != null && !(raw["AllowedOrigins"] is string))
                    {
                        foreach (object value in values)
                        {
                            string origin = Convert.ToString(value).Trim().TrimEnd('/');
                            if (origin.Length > 0) origins.Add(origin);
                        }
                    }
                }
            }
        }
        Uri appUri;
        if (!Uri.TryCreate(appUrl, UriKind.Absolute, out appUri)
            || (appUri.Scheme != Uri.UriSchemeHttps
                && !(appUri.IsLoopback && appUri.Scheme == Uri.UriSchemeHttp)))
        {
            throw new InvalidDataException("The Sports Cave OS URL is invalid.");
        }
        origins.Add(appUri.GetLeftPart(UriPartial.Authority).TrimEnd('/'));
        origins.Add("https://sports-cave-image-factory.onrender.com");
        if (rootPath.Length > 0)
        {
            try
            {
                rootPath = Path.GetFullPath(rootPath).TrimEnd(
                    Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                if (!Directory.Exists(rootPath)) rootPath = "";
            }
            catch
            {
                rootPath = "";
            }
        }
        return new DesktopConfig
        {
            AppUrl = appUrl,
            RootPath = rootPath,
            AllowedOrigins = origins,
        };
    }

    internal bool Allows(string value)
    {
        Uri uri;
        return Uri.TryCreate(value, UriKind.Absolute, out uri)
            && AllowedOrigins.Contains(uri.GetLeftPart(UriPartial.Authority).TrimEnd('/'));
    }
}

internal sealed class DesktopWindow : Window
{
    private readonly DesktopConfig config;
    private readonly WebView2 browser;
    private readonly JavaScriptSerializer serializer = new JavaScriptSerializer();
    private readonly NativeCache cache;
    private readonly Dictionary<string, CancellationTokenSource> operations =
        new Dictionary<string, CancellationTokenSource>(StringComparer.Ordinal);
    private readonly string initialUrl;
    private readonly bool persistent;
    private readonly bool deferInitialNavigation;
    private CoreWebView2Environment environment;
    private DesktopWindow imageViewerWindow;
    private string pendingTrustedNavigation = "";
    private Task browserInitializationTask;
    private bool browserConfigured;
    private bool browserInitialized;
    private bool browserFailureReported;
    private bool redirectedForSignIn;
    private bool navigateFilesWhenReady;

    internal DesktopWindow(
        DesktopConfig desktopConfig, string requestedUrl = "", bool keepResident = true,
        CoreWebView2Environment sharedEnvironment = null,
        bool waitForOpenerNavigation = false)
    {
        config = desktopConfig;
        cache = new NativeCache(config.RootPath);
        environment = sharedEnvironment;
        deferInitialNavigation = waitForOpenerNavigation;
        initialUrl = deferInitialNavigation
            ? ""
            : (String.IsNullOrWhiteSpace(requestedUrl) ? config.AppUrl : requestedUrl);
        persistent = keepResident;
        Title = "Sports Cave Files";
        Icon = LoadFilesIcon();
        Width = 1420;
        Height = 900;
        MinWidth = 900;
        MinHeight = 620;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;
        browser = new WebView2();
        Content = browser;
        Loaded += OnLoaded;
        Closing += delegate(object sender, System.ComponentModel.CancelEventArgs args)
        {
            if (persistent)
            {
                args.Cancel = true;
                Hide();
            }
        };
    }

    private static ImageSource LoadFilesIcon()
    {
        try
        {
            string iconPath = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory,
                "SportsCaveFiles.ico");
            if (!File.Exists(iconPath)) return null;
            return BitmapFrame.Create(
                new Uri(iconPath, UriKind.Absolute),
                BitmapCreateOptions.None,
                BitmapCacheOption.OnLoad);
        }
        catch
        {
            return null;
        }
    }

    private async void OnLoaded(object sender, RoutedEventArgs args)
    {
        try
        {
            await InitializeBrowser();
        }
        catch (Exception error)
        {
            ReportBrowserFailure(error);
        }
    }

    private async Task InitializeBrowser()
    {
        if (browserInitialized) return;
        if (browserInitializationTask == null)
        {
            browserInitializationTask = InitializeBrowserCore();
        }
        Task pending = browserInitializationTask;
        try
        {
            await pending;
        }
        catch
        {
            if (ReferenceEquals(browserInitializationTask, pending))
            {
                browserInitializationTask = null;
            }
            throw;
        }
    }

    private async Task InitializeBrowserCore()
    {
        string userData = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "SportsCaveOS", "WebView2");
        Directory.CreateDirectory(userData);
        if (environment == null)
        {
            environment = await CoreWebView2Environment.CreateAsync(null, userData);
        }
        await browser.EnsureCoreWebView2Async(environment);
        if (!browserConfigured)
        {
            browser.CoreWebView2.Settings.AreDevToolsEnabled = false;
            browser.CoreWebView2.Settings.AreHostObjectsAllowed = false;
            browser.CoreWebView2.Settings.IsPasswordAutosaveEnabled = true;
            browser.CoreWebView2.Settings.IsGeneralAutofillEnabled = true;
            browser.CoreWebView2.WebMessageReceived += OnWebMessage;
            browser.CoreWebView2.NavigationStarting += delegate(
                object navigationSender, CoreWebView2NavigationStartingEventArgs navigationArgs)
            {
                if (
                    !navigationArgs.Uri.Equals("about:blank", StringComparison.OrdinalIgnoreCase)
                    && !config.Allows(navigationArgs.Uri)
                )
                {
                    navigationArgs.Cancel = true;
                }
            };
            browser.CoreWebView2.NavigationCompleted += delegate(
                object navigationSender, CoreWebView2NavigationCompletedEventArgs navigationArgs)
            {
                Uri current = browser.Source;
                if (
                    !redirectedForSignIn
                    && navigationArgs.HttpStatusCode == 403
                    && current != null
                    && current.AbsolutePath.Equals(
                        "/files-window", StringComparison.OrdinalIgnoreCase)
                )
                {
                    redirectedForSignIn = true;
                    browser.CoreWebView2.Navigate(
                        current.GetLeftPart(UriPartial.Authority) + "/");
                }
            };
            browser.CoreWebView2.NewWindowRequested += async delegate(
                object windowSender, CoreWebView2NewWindowRequestedEventArgs windowArgs)
            {
                CoreWebView2Deferral deferral = windowArgs.GetDeferral();
                DesktopWindow child = null;
                windowArgs.Handled = true;
                try
                {
                    bool blank = windowArgs.Uri.Equals(
                        "about:blank", StringComparison.OrdinalIgnoreCase);
                    if (blank || config.Allows(windowArgs.Uri))
                    {
                        child = new DesktopWindow(
                            config,
                            blank ? "" : windowArgs.Uri,
                            false,
                            environment,
                            blank);
                        child.Show();
                        await child.InitializeBrowser();
                        windowArgs.NewWindow = child.browser.CoreWebView2;
                    }
                }
                catch (Exception error)
                {
                    if (child != null) child.Close();
                    DesktopLog.Write("newWindow", "failed", error.GetType().Name, 0);
                }
                finally
                {
                    deferral.Complete();
                }
            };
            browser.CoreWebView2.ContextMenuRequested += OnContextMenuRequested;
            browserConfigured = true;
        }
        if (!deferInitialNavigation)
        {
            browser.CoreWebView2.Navigate(initialUrl);
        }
        if (!String.IsNullOrWhiteSpace(pendingTrustedNavigation))
        {
            string pending = pendingTrustedNavigation;
            pendingTrustedNavigation = "";
            browser.CoreWebView2.Navigate(pending);
        }
        if (navigateFilesWhenReady)
        {
            NavigateToFiles(false);
        }
        browserInitialized = true;
    }

    private void ReportBrowserFailure(Exception error)
    {
        DesktopLog.Write("webview", "failed", error.GetType().Name, 0);
        if (browserFailureReported) return;
        browserFailureReported = true;
        MessageBox.Show(
            "Sports Cave Desktop could not open this window. Reinstall the desktop helper.",
            "Sports Cave OS Desktop", MessageBoxButton.OK, MessageBoxImage.Error);
    }

    internal void ShowAndFocus()
    {
        if (!IsVisible) Show();
        if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal;
        Activate();
        Topmost = true;
        Topmost = false;
        Focus();
    }

    internal void NavigateToFiles()
    {
        NavigateToFiles(true);
    }

    private void NavigateToFiles(bool allowReload)
    {
        navigateFilesWhenReady = true;
        ShowAndFocus();
        if (browser.CoreWebView2 == null) return;
        Uri appUri = new Uri(config.AppUrl);
        string filesUrl = appUri.GetLeftPart(UriPartial.Authority) + "/files-window";
        Uri current = browser.Source;
        if (
            !allowReload
            || (
                current != null
                && current.GetLeftPart(UriPartial.Authority).Equals(
                    appUri.GetLeftPart(UriPartial.Authority),
                    StringComparison.OrdinalIgnoreCase)
                && current.AbsolutePath.Equals("/files-window", StringComparison.OrdinalIgnoreCase)
            )
        )
        {
            return;
        }
        browser.CoreWebView2.Navigate(filesUrl);
    }

    private void OnContextMenuRequested(
        object sender, CoreWebView2ContextMenuRequestedEventArgs args)
    {
        Uri current = browser.Source;
        if (
            current == null
            || !current.AbsolutePath.Equals(
                "/files-image-viewer", StringComparison.OrdinalIgnoreCase)
            || args.ContextMenuTarget == null
            || !args.ContextMenuTarget.HasSourceUri
            || args.MenuItems.Any(item => String.Equals(
                item.Label, "Copy image", StringComparison.OrdinalIgnoreCase))
        )
        {
            return;
        }
        CoreWebView2ContextMenuItem copyImage = environment.CreateContextMenuItem(
            "Copy image", null, CoreWebView2ContextMenuItemKind.Command);
        copyImage.CustomItemSelected += delegate
        {
            Dispatcher.BeginInvoke(new Action(async delegate
            {
                try
                {
                    await browser.CoreWebView2.ExecuteScriptAsync(
                        "window.sportsCaveCopyImagePixels && window.sportsCaveCopyImagePixels()");
                }
                catch (Exception error)
                {
                    DesktopLog.Write(
                        "copyImage", "failed", error.GetType().Name, 0);
                }
            }));
        };
        args.MenuItems.Insert(0, copyImage);
    }

    private static string ViewerRelativeValue(
        Dictionary<string, object> viewer, string key, bool required)
    {
        string value = viewer.ContainsKey(key)
            ? Convert.ToString(viewer[key]) : "";
        if (String.IsNullOrWhiteSpace(value))
        {
            if (required)
            {
                throw new DesktopException(
                    "viewer_path_invalid", "The selected image path is invalid.");
            }
            return "";
        }
        if (
            value.Length > 1024
            || value.IndexOfAny(new[] { '\0', '\r', '\n' }) >= 0
            || value.Contains("\\")
            || value.Contains(":")
            || value.StartsWith("/", StringComparison.Ordinal)
            || value.Split('/').Any(part =>
                String.IsNullOrWhiteSpace(part) || part == "." || part == "..")
        )
        {
            throw new DesktopException(
                "viewer_path_invalid", "The selected image path is invalid.");
        }
        return value;
    }

    private static string ViewerName(
        Dictionary<string, object> viewer, string fallback)
    {
        string name = viewer.ContainsKey("name")
            ? Convert.ToString(viewer["name"]) : "";
        if (
            String.IsNullOrWhiteSpace(name)
            || name.Length > 260
            || name.IndexOfAny(new[] { '\0', '\r', '\n' }) >= 0
        )
        {
            return fallback;
        }
        return name;
    }

    private async Task OpenImageViewer(Dictionary<string, object> viewer)
    {
        string path = ViewerRelativeValue(viewer, "path", true);
        string extension = Path.GetExtension(path).ToLowerInvariant();
        if (!new[] { ".jpg", ".jpeg", ".png", ".webp", ".gif" }.Contains(extension))
        {
            throw new DesktopException(
                "viewer_image_required", "Select an image to open in the viewer.");
        }
        string folder = ViewerRelativeValue(viewer, "folder", false);
        string name = ViewerName(viewer, path.Split('/').Last());
        Uri appUri = new Uri(config.AppUrl);
        string viewerUrl = appUri.GetLeftPart(UriPartial.Authority)
            + "/files-image-viewer?path=" + Uri.EscapeDataString(path)
            + "&folder=" + Uri.EscapeDataString(folder)
            + "&name=" + Uri.EscapeDataString(name);

        if (imageViewerWindow == null || !imageViewerWindow.IsLoaded)
        {
            var child = new DesktopWindow(config, viewerUrl, false, environment);
            imageViewerWindow = child;
            child.Closed += delegate
            {
                if (ReferenceEquals(imageViewerWindow, child))
                {
                    imageViewerWindow = null;
                }
            };
            child.Show();
            try
            {
                await child.InitializeBrowser();
            }
            catch
            {
                child.Close();
                throw;
            }
        }
        else
        {
            try
            {
                await imageViewerWindow.InitializeBrowser();
                imageViewerWindow.NavigateTrusted(viewerUrl);
            }
            catch
            {
                imageViewerWindow.Close();
                imageViewerWindow = null;
                throw;
            }
        }
        imageViewerWindow.ShowAndFocus();
    }

    private void NavigateTrusted(string url)
    {
        if (!config.Allows(url))
        {
            throw new DesktopException(
                "navigation_denied", "This desktop navigation is not allowed.");
        }
        if (browser.CoreWebView2 == null)
        {
            pendingTrustedNavigation = url;
            return;
        }
        browser.CoreWebView2.Navigate(url);
    }

    private async void OnWebMessage(object sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        string action = "message";
        string requestId = "";
        try
        {
            if (!config.Allows(args.Source))
            {
                throw new DesktopException("origin_denied", "This page cannot use the desktop bridge.");
            }
            var message = serializer.DeserializeObject(args.WebMessageAsJson)
                as Dictionary<string, object>;
            if (message == null || !message.ContainsKey("action"))
            {
                throw new DesktopException("invalid_message", "The desktop request is invalid.");
            }
            action = Convert.ToString(message["action"]);
            requestId = message.ContainsKey("request_id")
                ? Convert.ToString(message["request_id"]) : "";
            if (action == "hello")
            {
                Reply("capabilities", requestId, true, new Dictionary<string, object>
                {
                    { "version", Program.HelperVersion },
                    { "capabilities", new[] { "drag", "copyFile", "copyImage", "openFile", "openWith", "verifiedOpen", "appDefaults", "openPhotoshop", "openPsdApp", "openViewer", "folders", "cancel" } },
                });
                return;
            }
            if (action == "cancel")
            {
                CancellationTokenSource pending;
                if (operations.TryGetValue(requestId, out pending)) pending.Cancel();
                Reply(action, requestId, true, null);
                return;
            }
            // Premium files: explicit OS preference UI, no association writes.
            if (action == "appDefaults")
            {
                if (requestId.Length < 8 || requestId.Length > 80 || message.Keys.Any(key => key != "action" && key != "request_id"))
                    throw new DesktopException("invalid_request", "The desktop request is invalid.");
                try { Process.Start(NativeFileOpening.DefaultAppsInfo()); }
                catch (System.ComponentModel.Win32Exception) { throw new DesktopException("settings_unavailable", "Open Windows Settings, then Apps and Default apps to choose or reset your application preference."); }
                Reply(action, requestId, true, null);
                return;
            }
            // End premium preference UI.
            if (action == "openViewer")
            {
                if (requestId.Length < 8 || requestId.Length > 80)
                {
                    throw new DesktopException(
                        "invalid_request", "The desktop request is invalid.");
                }
                var viewer = message.ContainsKey("viewer")
                    ? message["viewer"] as Dictionary<string, object> : null;
                if (viewer == null || HasUnexpectedKeys(viewer))
                {
                    throw new DesktopException(
                        "viewer_request_invalid", "The image viewer request is invalid.");
                }
                await OpenImageViewer(viewer);
                Reply(action, requestId, true, null);
                DesktopLog.Write(action, "completed", "none", 1);
                return;
            }
            if (action != "drag" && action != "copyFile"
                && action != "copyImage" && action != "openFile" && action != "openWith" && action != "openPhotoshop" && action != "openPsdApp")
            {
                throw new DesktopException("action_denied", "The desktop action is not allowed.");
            }
            if (requestId.Length < 8 || requestId.Length > 80 || operations.ContainsKey(requestId))
            {
                throw new DesktopException("invalid_request", "The desktop request is invalid.");
            }
            TransferGrant grant = TransferGrant.FromMessage(message, config);
            var cancellation = new CancellationTokenSource();
            operations[requestId] = cancellation;
            try
            {
                string photoshop = action == "openPhotoshop" ? NativePhotoshop.FindRequiredApplication() : "";
                string[] paths = (action == "openPhotoshop" || action == "openPsdApp")
                    ? await cache.MaterializePhotoshopAsync(grant, cancellation.Token)
                    : await cache.MaterializeAsync(
                    grant,
                    cancellation.Token,
                    delegate(long complete, long total, string name)
                    {
                        Dispatcher.BeginInvoke(new Action(delegate
                        {
                            Reply("progress", requestId, true, new Dictionary<string, object>
                            {
                                { "complete", complete }, { "total", total }, { "name", name },
                            });
                        }));
                    });
                if (action == "drag")
                {
                    if ((NativeMethods.GetAsyncKeyState(1) & 0x8000) == 0)
                    {
                        throw new DesktopException(
                            "drag_cancelled",
                            "Keep holding the mouse while the selected files are prepared.");
                    }
                    var data = NativePayload.Create(paths);
                    DragDropEffects effect = System.Windows.DragDrop.DoDragDrop(
                        this, data, DragDropEffects.Copy);
                    Reply(action, requestId, true, new Dictionary<string, object>
                    {
                        { "count", paths.Length },
                        { "effect", effect == DragDropEffects.Copy ? "copy" : "cancelled" },
                    });
                }
                else if (action == "copyFile")
                {
                    var data = NativePayload.Create(paths);
                    SetClipboardData(data);
                    Reply(action, requestId, true, new Dictionary<string, object>
                    {
                        { "count", paths.Length },
                    });
                }
                // Premium files: chooser uses the existing validated transfer/cache path.
                else if (action == "openWith")
                {
                    if (paths.Length != 1) throw new DesktopException("one_file_required", "Select one file for Open With.");
                    cancellation.Token.ThrowIfCancellationRequested();
                    NativeFileOpening.OpenWith(paths[0],new System.Windows.Interop.WindowInteropHelper(this).Handle);
                    Reply(action, requestId, true, new Dictionary<string,object> { { "count",1 } });
                }
                // End premium chooser.
                else if (action == "copyImage")
                {
                    if (paths.Length != 1 || Directory.Exists(paths[0]))
                    {
                        throw new DesktopException("image_required", "Select one image to copy.");
                    }
                    SetImageClipboard(paths[0]);
                    Reply(action, requestId, true, new Dictionary<string, object>
                    {
                        { "count", 1 },
                    });
                }
                else if (action == "openPsdApp")
                {
                    if (paths.Length != 1) throw new DesktopException("master_required", "Select one linked master.");
                    cancellation.Token.ThrowIfCancellationRequested();
                    try { Process.Start(NativePhotoshop.DefaultAppStartInfo(paths[0])); }
                    catch (System.ComponentModel.Win32Exception) { throw new DesktopException("psd_app_unavailable", "Windows has no available PSD application. Choose a default app for .psd in Windows Settings, or select Photoshop and retry."); }
                    Reply(action, requestId, true, new Dictionary<string, object> { { "count", 1 } });
                }
                else if (action == "openPhotoshop")
                {
                    if (paths.Length != 1) throw new DesktopException("master_required", "Select one linked master.");
                    cancellation.Token.ThrowIfCancellationRequested();
                    try { Process.Start(NativePhotoshop.StartInfo(photoshop, paths[0])); }
                    catch (System.ComponentModel.Win32Exception) { throw new DesktopException("photoshop_launch_failed", "Windows could not start Adobe Photoshop. Open Photoshop once, check Windows permissions, then retry."); }
                    Reply(action, requestId, true, new Dictionary<string, object> { { "count", 1 } });
                }
                else
                {
                    foreach (string path in paths)
                    {
                        if (File.Exists(path)) NativeFileOpening.CheckType(path);
                        cancellation.Token.ThrowIfCancellationRequested();
                        try { Process.Start(new ProcessStartInfo(path) { UseShellExecute = true }); }
                        catch (System.ComponentModel.Win32Exception) { throw new DesktopException("application_unavailable", "Windows could not open the file. Use Open With to choose an installed application, or check file permissions."); }
                    }
                    Reply(action, requestId, true, new Dictionary<string, object>
                    {
                        { "count", paths.Length },
                    });
                }
                DesktopLog.Write(action, "completed", "none", paths.Length);
            }
            finally
            {
                operations.Remove(requestId);
                cancellation.Dispose();
            }
        }
        catch (OperationCanceledException)
        {
            Reply(action, requestId, false, Error("cancelled", "The desktop transfer was cancelled."));
        }
        catch (DesktopException error)
        {
            Reply(action, requestId, false, Error(error.Code, error.Message));
            DesktopLog.Write(action, "failed", error.Code, 0);
        }
        catch (Exception error)
        {
            Reply(action, requestId, false, Error(
                "desktop_error", "Sports Cave Desktop could not complete this action."));
            DesktopLog.Write(action, "failed", error.GetType().Name, 0);
        }
    }

    private static bool HasUnexpectedKeys(Dictionary<string, object> values)
    {
        return values.Keys.Any(key =>
            key != "path" && key != "folder" && key != "name");
    }

    private static Dictionary<string, object> Error(string code, string message)
    {
        return new Dictionary<string, object> { { "code", code }, { "message", message } };
    }

    private void Reply(
        string action, string requestId, bool ok, Dictionary<string, object> values)
    {
        if (browser.CoreWebView2 == null) return;
        var message = values ?? new Dictionary<string, object>();
        message["type"] = "sports-cave-desktop";
        message["action"] = action;
        message["request_id"] = requestId;
        message["ok"] = ok;
        browser.CoreWebView2.PostWebMessageAsJson(serializer.Serialize(message));
    }

    private static void SetImageClipboard(string path)
    {
        var bitmap = new BitmapImage();
        using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
        {
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.StreamSource = stream;
            bitmap.EndInit();
            bitmap.Freeze();
        }
        BitmapSource clipboardBitmap;
        if (bitmap.Format == PixelFormats.Bgra32)
        {
            clipboardBitmap = bitmap;
        }
        else
        {
            clipboardBitmap = new FormatConvertedBitmap(
                bitmap, PixelFormats.Bgra32, null, 0);
        }
        if (clipboardBitmap.CanFreeze) clipboardBitmap.Freeze();
        var data = new System.Windows.DataObject();
        data.SetImage(clipboardBitmap);
        data.SetData(
            System.Windows.DataFormats.Dib,
            CreateDib(clipboardBitmap),
            false);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        var png = new MemoryStream();
        encoder.Save(png);
        png.Position = 0;
        data.SetData("PNG", png, false);
        SetClipboardData(data);
    }

    private static MemoryStream CreateDib(BitmapSource bitmap)
    {
        int width = bitmap.PixelWidth;
        int height = bitmap.PixelHeight;
        int stride = checked(width * 4);
        byte[] pixels = new byte[checked(stride * height)];
        bitmap.CopyPixels(pixels, stride, 0);
        var stream = new MemoryStream(40 + pixels.Length);
        using (var writer = new BinaryWriter(stream, Encoding.UTF8, true))
        {
            writer.Write(40);
            writer.Write(width);
            writer.Write(height);
            writer.Write((short)1);
            writer.Write((short)32);
            writer.Write(0);
            writer.Write(pixels.Length);
            writer.Write(0);
            writer.Write(0);
            writer.Write(0);
            writer.Write(0);
            for (int row = height - 1; row >= 0; row--)
            {
                writer.Write(pixels, row * stride, stride);
            }
        }
        stream.Position = 0;
        return stream;
    }

    private static void SetClipboardData(System.Windows.DataObject data)
    {
        for (int attempt = 0; attempt < 8; attempt++)
        {
            try
            {
                System.Windows.Clipboard.SetDataObject(data, true);
                return;
            }
            catch (COMException)
            {
                if (attempt == 7)
                {
                    throw new DesktopException(
                        "clipboard_busy",
                        "Windows clipboard is busy. Wait a moment and copy again.");
                }
                Thread.Sleep(35 * (attempt + 1));
            }
        }
    }
}

internal sealed class TransferGrant
{
    internal string BaseUrl;
    internal string Ticket;
    internal string Secret;

    internal static TransferGrant FromMessage(
        Dictionary<string, object> message, DesktopConfig config)
    {
        var transfer = message.ContainsKey("transfer")
            ? message["transfer"] as Dictionary<string, object> : null;
        if (transfer == null || transfer.Count != 3
            || !transfer.ContainsKey("base_url")
            || !transfer.ContainsKey("ticket")
            || !transfer.ContainsKey("secret"))
        {
            throw new DesktopException("invalid_transfer", "The desktop transfer grant is invalid.");
        }
        string baseUrl = Convert.ToString(transfer["base_url"]).TrimEnd('/');
        string ticket = Convert.ToString(transfer["ticket"]);
        string secret = Convert.ToString(transfer["secret"]);
        if (!config.Allows(baseUrl) || ticket.Length < 20 || secret.Length < 30)
        {
            throw new DesktopException("invalid_transfer", "The desktop transfer grant is invalid.");
        }
        return new TransferGrant { BaseUrl = baseUrl, Ticket = ticket, Secret = secret };
    }
}

internal sealed class NativeCache
{
    private readonly string root;
    private readonly string localRoot;
    private readonly JavaScriptSerializer serializer = new JavaScriptSerializer();
    private readonly HttpClient client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false });

    internal NativeCache(string configuredRoot = "")
    {
        string testRoot = Convert.ToString(
            Environment.GetEnvironmentVariable("SPORTS_CAVE_FILE_CACHE"));
        root = String.IsNullOrWhiteSpace(testRoot)
            ? Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "SportsCaveOS", "FileCache")
            : Path.GetFullPath(testRoot);
        client.Timeout = Timeout.InfiniteTimeSpan; // Large streams remain cancellable; never buffer a master.
        localRoot = ResolveConfiguredRoot(configuredRoot);
        Directory.CreateDirectory(root);
        CleanupExpired();
    }

    internal async Task<string[]> MaterializePhotoshopAsync(TransferGrant grant, CancellationToken cancellation)
    {
        var manifest = await GetJson(grant.BaseUrl + "/api/files-native-transfer/manifest?ticket=" + Uri.EscapeDataString(grant.Ticket), grant.Secret, cancellation);
        string target = ResolvePhotoshopMaster(manifest);
        var items = manifest["items"] as IList;
        var item = items[0] as Dictionary<string, object>;
        await NativePhotoshop.VerifyMasterAsync(target, localRoot, Convert.ToInt64(item["size"]), Convert.ToString(item["content_hash"]), cancellation);
        return new[] { target };
    }

    internal string ResolvePhotoshopMaster(Dictionary<string, object> manifest)
    {
        if (!manifest.ContainsKey("purpose") || Convert.ToString(manifest["purpose"]) != "photoshop_master")
            throw new DesktopException("master_required", "A verified linked master transfer is required.");
        var items = manifest.ContainsKey("items") ? manifest["items"] as IList : null;
        var roots = manifest.ContainsKey("roots") ? manifest["roots"] as IList : null;
        if (items == null || roots == null || items.Count != 1 || roots.Count != 1)
            throw new DesktopException("master_required", "Only one linked PSD master can be opened.");
        var item = items[0] as Dictionary<string, object>;
        var entry = roots[0] as Dictionary<string, object>;
        if (item == null || entry == null || Convert.ToBoolean(item["is_directory"]) || Convert.ToBoolean(entry["is_directory"])
            || !item.ContainsKey("content_hash") || !item.ContainsKey("dropbox_id")
            || !System.Text.RegularExpressions.Regex.IsMatch(Convert.ToString(item["dropbox_id"]), "^id:[A-Za-z0-9_-]+$")
            || !IsHex(Convert.ToString(item["content_hash"]),64))
            throw new DesktopException("manifest_invalid", "The linked master verification metadata is invalid.");
        string relative = SafeLocalRelativePath(Convert.ToString(entry["source_relative_path"]));
        string[] parts = relative.Split(Path.DirectorySeparatorChar);
        if (parts.Length != 3 || !parts[0].Equals("02_TASKS",StringComparison.OrdinalIgnoreCase)
            || !parts[1].Equals("03_DESIGNS-LIVE-ONLINE-UPLOADED",StringComparison.OrdinalIgnoreCase)
            || !Path.GetExtension(parts[2]).Equals(".psd",StringComparison.OrdinalIgnoreCase)
            || !parts[2].Equals(Convert.ToString(item["name"]),StringComparison.Ordinal))
            throw new DesktopException("master_scope_denied", "Only an approved main-folder PSD master can be opened.");
        if (String.IsNullOrWhiteSpace(localRoot))
            throw new DesktopException("dropbox_sync_unavailable", "Configure the locally synced Sportscave Team Folder using the existing Desktop installer, then retry.");
        string target = Path.GetFullPath(Path.Combine(localRoot,relative));
        EnsureInside(localRoot,target);
        if (!File.Exists(target))
            throw new DesktopException("master_not_synced", "This linked master is not available locally. Sync the approved PSD folder in Dropbox Desktop, wait for the renamed file if necessary, then retry.");
        return target;
    }

    internal async Task<string[]> MaterializeAsync(
        TransferGrant grant,
        CancellationToken cancellation,
        Action<long, long, string> progress)
    {
        Dictionary<string, object> manifest = await GetJson(
            grant.BaseUrl + "/api/files-native-transfer/manifest?ticket="
                + Uri.EscapeDataString(grant.Ticket),
            grant.Secret,
            cancellation);
        if (manifest.ContainsKey("purpose") && Convert.ToString(manifest["purpose"]) == "native_open")
            return await MaterializeNativeOpenAsync(grant, manifest, cancellation, progress);
        string[] localPaths = ResolveLocalRoots(manifest);
        if (localPaths.Length > 0)
        {
            if (progress != null) progress(localPaths.Length, localPaths.Length, "");
            return localPaths;
        }
        var items = manifest["items"] as IList;
        if (items == null) throw new DesktopException("manifest_invalid", "The transfer manifest is invalid.");
        long total = Convert.ToInt64(manifest["total_bytes"]);
        long complete = 0;
        string lease = Path.Combine(root, "leases", grant.Ticket);
        Directory.CreateDirectory(lease);
        File.WriteAllText(Path.Combine(lease, ".active"), DateTime.UtcNow.ToString("o"));
        var roots = new List<string>();
        var seenRoots = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        try
        {
            foreach (object raw in items)
            {
                cancellation.ThrowIfCancellationRequested();
                var item = raw as Dictionary<string, object>;
                if (item == null) throw new DesktopException("manifest_invalid", "The transfer manifest is invalid.");
                string relative = SafeRelativePath(Convert.ToString(item["relative_path"]));
                string target = Path.GetFullPath(Path.Combine(lease, relative));
                EnsureInside(lease, target);
                string top = relative.Split(Path.DirectorySeparatorChar)[0];
                string topPath = Path.Combine(lease, top);
                if (seenRoots.Add(topPath)) roots.Add(topPath);
                bool directory = Convert.ToBoolean(item["is_directory"]);
                if (directory)
                {
                    Directory.CreateDirectory(target);
                    continue;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(target));
                string cacheKey = Convert.ToString(item["cache_key"]);
                if (!IsHex(cacheKey, 64))
                {
                    throw new DesktopException("manifest_invalid", "The transfer manifest is invalid.");
                }
                string objectFolder = Path.Combine(root, "objects", cacheKey.Substring(0, 2), cacheKey);
                Directory.CreateDirectory(objectFolder);
                string objectPath = Path.Combine(objectFolder, SafeSegment(Convert.ToString(item["name"])));
                long size = Convert.ToInt64(item["size"]);
                if (!File.Exists(objectPath) || new FileInfo(objectPath).Length != size)
                {
                    string partial = objectPath + ".partial-" + Guid.NewGuid().ToString("N");
                    try
                    {
                        await Download(
                            grant.BaseUrl + "/api/files-native-transfer/content?ticket="
                                + Uri.EscapeDataString(grant.Ticket)
                                + "&item=" + Uri.EscapeDataString(Convert.ToString(item["token"])),
                            grant.Secret, partial, cancellation,
                            delegate(long amount)
                            {
                                if (progress != null) progress(complete + amount, total, Convert.ToString(item["name"]));
                            });
                        if (File.Exists(objectPath)) File.Delete(objectPath);
                        File.Move(partial, objectPath);
                    }
                    finally
                    {
                        if (File.Exists(partial)) File.Delete(partial);
                    }
                }
                if (File.Exists(target)) File.Delete(target);
                if (!NativeMethods.CreateHardLink(target, objectPath, IntPtr.Zero))
                {
                    File.Copy(objectPath, target, true);
                }
                complete += size;
                if (progress != null) progress(complete, total, Convert.ToString(item["name"]));
                File.SetLastWriteTimeUtc(objectPath, DateTime.UtcNow);
            }
            File.Delete(Path.Combine(lease, ".active"));
            File.WriteAllText(Path.Combine(lease, ".lease"), DateTime.UtcNow.AddDays(3).ToString("o"));
            Directory.SetLastWriteTimeUtc(lease, DateTime.UtcNow);
            return roots.ToArray();
        }
        catch
        {
            try { File.Delete(Path.Combine(lease, ".active")); } catch { }
            throw;
        }
    }

    internal async Task<string[]> MaterializeNativeOpenAsync(TransferGrant grant,
        Dictionary<string,object> manifest, CancellationToken cancellation, Action<long,long,string> progress)
    {
        var items = manifest.ContainsKey("items") ? manifest["items"] as IList : null;
        var entries = manifest.ContainsKey("roots") ? manifest["roots"] as IList : null;
        if (items == null || entries == null || items.Count != 1 || entries.Count != 1)
            throw new DesktopException("manifest_invalid", "Select one verified file for native opening.");
        var item = items[0] as Dictionary<string,object>;
        var entry = entries[0] as Dictionary<string,object>;
        if (item == null || entry == null || Convert.ToBoolean(item["is_directory"]) || Convert.ToBoolean(entry["is_directory"])
            || !item.ContainsKey("content_hash") || !item.ContainsKey("dropbox_id")
            || !System.Text.RegularExpressions.Regex.IsMatch(Convert.ToString(item["dropbox_id"]), "^id:[A-Za-z0-9_-]+$")
            || !IsHex(Convert.ToString(item["content_hash"]),64) || !IsHex(Convert.ToString(item["cache_key"]),64)
            || String.IsNullOrEmpty(Convert.ToString(item["revision"]))
            || !String.Equals(Convert.ToString(entry["revision"]),Convert.ToString(item["revision"]),StringComparison.Ordinal))
            throw new DesktopException("manifest_invalid", "The file identity/revision cannot be verified.");
        string name = SafeLocalRelativePath(Convert.ToString(item["name"]));
        string relative = SafeLocalRelativePath(Convert.ToString(entry["source_relative_path"]));
        if (name.IndexOf(Path.DirectorySeparatorChar) >= 0 || !Path.GetFileName(relative).Equals(name,StringComparison.Ordinal))
            throw new DesktopException("unsafe_path", "The selected file location is invalid.");
        foreach (string segment in relative.Split(Path.DirectorySeparatorChar))
            if (segment.EndsWith(".") || segment.EndsWith(" "))
                throw new DesktopException("unsafe_path", "This filename cannot be safely opened on Windows. Use browser Download.");
        NativeFileOpening.CheckType(name);
        long size = Convert.ToInt64(item["size"]);
        if (size < 0) throw new DesktopException("manifest_invalid", "Invalid file size.");
        string hash = Convert.ToString(item["content_hash"]);
        if (progress != null) progress(0,size,name);
        if (!String.IsNullOrWhiteSpace(localRoot))
        {
            string synced = Path.GetFullPath(Path.Combine(localRoot,relative));
            EnsureInside(localRoot,synced);
            if (File.Exists(synced))
            {
                try {
                    await NativePhotoshop.VerifyMasterAsync(synced,localRoot,size,hash,cancellation);
                    if (progress != null) progress(size,size,name);
                    return new[] {synced};
                }
                catch (DesktopException error) {
                    // A stale/missing/cloud-offline local revision is never opened or changed.
                    if (error.Code != "master_sync_pending" && error.Code != "master_hydration_failed") throw;
                }
            }
        }
        string cacheKey = Convert.ToString(item["cache_key"]);
        string folder = Path.Combine(root,"objects",cacheKey.Substring(0,2),cacheKey);
        string target = Path.Combine(folder,name);
        Directory.CreateDirectory(folder); EnsureInside(root,target);
        // Validate the resolved directory before any cache write (reject reparse/symlink escape).
        string directory = folder;
        while (directory.Length >= root.Length) {
            if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
                throw new DesktopException("unsafe_path", "The cache folder is not safe.");
            if (directory.Equals(root,StringComparison.OrdinalIgnoreCase)) break;
            directory = Path.GetDirectoryName(directory);
        }
        if (!File.Exists(target))
        {
            // Filename changes do not invalidate an immutable ID/revision cache object.
            foreach (string prior in Directory.GetFiles(folder))
            {
                if (!Path.GetExtension(prior).Equals(Path.GetExtension(name),StringComparison.OrdinalIgnoreCase)) continue;
                try {
                    await NativePhotoshop.VerifyMasterAsync(prior,root,size,hash,cancellation);
                    if (!NativeMethods.CreateHardLink(target,prior,IntPtr.Zero)) target = prior;
                    break;
                } catch (DesktopException error) {if (error.Code != "master_sync_pending") throw;}
            }
        }
        if (File.Exists(target))
        {
            try {
                await NativePhotoshop.VerifyMasterAsync(target,root,size,hash,cancellation);
                if (progress != null) progress(size,size,name);
                return new[] {target};
            } catch (DesktopException error) {
                if (error.Code != "master_sync_pending") throw;
            }
        }
        string partial = target+".partial-"+Guid.NewGuid().ToString("N");
        try {
            await Download(grant.BaseUrl+"/api/files-native-transfer/content?ticket="+Uri.EscapeDataString(grant.Ticket)
                +"&item="+Uri.EscapeDataString(Convert.ToString(item["token"])),grant.Secret,partial,cancellation,
                delegate(long done) {if (progress != null) progress(done,size,name);});
            await NativePhotoshop.VerifyMasterAsync(partial,root,size,hash,cancellation);
            cancellation.ThrowIfCancellationRequested();
            if (File.Exists(target)) File.Delete(target);
            File.Move(partial,target);
            return new[] {target};
        } finally {if (File.Exists(partial)) File.Delete(partial);}
    }

    private static string ResolveConfiguredRoot(string value)
    {
        if (String.IsNullOrWhiteSpace(value)) return "";
        try
        {
            string resolved = Path.GetFullPath(value).TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            return Directory.Exists(resolved) ? resolved : "";
        }
        catch
        {
            return "";
        }
    }

    private string[] ResolveLocalRoots(Dictionary<string, object> manifest)
    {
        if (String.IsNullOrWhiteSpace(localRoot)) return new string[0];
        var entries = manifest.ContainsKey("roots") ? manifest["roots"] as IList : null;
        if (entries == null || entries.Count == 0) return new string[0];
        var paths = new List<string>();
        foreach (object raw in entries)
        {
            var entry = raw as Dictionary<string, object>;
            if (entry == null || !entry.ContainsKey("source_relative_path")
                || !entry.ContainsKey("is_directory"))
            {
                return new string[0];
            }
            string relative = SafeLocalRelativePath(
                Convert.ToString(entry["source_relative_path"]));
            string target = Path.GetFullPath(Path.Combine(localRoot, relative));
            EnsureInside(localRoot, target);
            bool directory = Convert.ToBoolean(entry["is_directory"]);
            if ((directory && !Directory.Exists(target))
                || (!directory && !File.Exists(target)))
            {
                return new string[0];
            }
            paths.Add(target);
        }
        return paths.ToArray();
    }

    internal static string SafeLocalRelativePath(string value)
    {
        string raw = Convert.ToString(value);
        if (String.IsNullOrWhiteSpace(raw) || Path.IsPathRooted(raw)
            || raw.IndexOf(':') >= 0 || raw.IndexOf('\0') >= 0)
        {
            throw new DesktopException("unsafe_path", "A transfer path is unsafe.");
        }
        string normalized = raw.Replace('/', Path.DirectorySeparatorChar);
        string[] parts = normalized.Split(Path.DirectorySeparatorChar);
        var safe = new List<string>();
        var invalid = new HashSet<char>(Path.GetInvalidFileNameChars());
        foreach (string part in parts)
        {
            if (part.Length == 0 || part == "." || part == "..")
            {
                throw new DesktopException("unsafe_path", "A transfer path is unsafe.");
            }
            foreach (char character in part)
            {
                if (invalid.Contains(character) || Char.IsControl(character))
                {
                    throw new DesktopException("unsafe_path", "A transfer path is unsafe.");
                }
            }
            safe.Add(part);
        }
        return String.Join(Path.DirectorySeparatorChar.ToString(), safe.ToArray());
    }

    private async Task<Dictionary<string, object>> GetJson(
        string url, string secret, CancellationToken cancellation)
    {
        using (var request = new HttpRequestMessage(HttpMethod.Get, url))
        {
            request.Headers.Add("X-Sports-Cave-Transfer-Secret", secret);
            using (HttpResponseMessage response = await client.SendAsync(request, cancellation))
            {
                string body = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    throw new DesktopException("transfer_failed", "The selected Dropbox items could not be prepared.");
                }
                return serializer.DeserializeObject(body) as Dictionary<string, object>;
            }
        }
    }

    private async Task Download(
        string url, string secret, string destination, CancellationToken cancellation,
        Action<long> progress)
    {
        using (var request = new HttpRequestMessage(HttpMethod.Get, url))
        {
            request.Headers.Add("X-Sports-Cave-Transfer-Secret", secret);
            using (HttpResponseMessage response = await client.SendAsync(
                request, HttpCompletionOption.ResponseHeadersRead, cancellation))
            {
                if (!response.IsSuccessStatusCode)
                {
                    throw new DesktopException("transfer_failed", "A Dropbox file could not be downloaded.");
                }
                using (Stream input = await response.Content.ReadAsStreamAsync())
                using (var output = new FileStream(
                    destination, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                    128 * 1024, true))
                {
                    byte[] buffer = new byte[128 * 1024];
                    long complete = 0;
                    int read;
                    while ((read = await input.ReadAsync(buffer, 0, buffer.Length, cancellation)) > 0)
                    {
                        await output.WriteAsync(buffer, 0, read, cancellation);
                        complete += read;
                        if (progress != null) progress(complete);
                    }
                }
            }
        }
    }

    internal static string SafeRelativePath(string value)
    {
        string raw = Convert.ToString(value);
        if (String.IsNullOrWhiteSpace(raw) || Path.IsPathRooted(raw)
            || raw.IndexOf('\\') >= 0 || raw.IndexOf(':') >= 0 || raw.IndexOf('\0') >= 0)
        {
            throw new DesktopException("unsafe_path", "A transfer path is unsafe.");
        }
        string[] parts = raw.Split('/');
        var safe = new List<string>();
        foreach (string part in parts)
        {
            if (part.Length == 0 || part == "." || part == "..")
            {
                throw new DesktopException("unsafe_path", "A transfer path is unsafe.");
            }
            safe.Add(SafeSegment(part));
        }
        return String.Join(Path.DirectorySeparatorChar.ToString(), safe.ToArray());
    }

    internal static string SafeSegment(string value)
    {
        string raw = Convert.ToString(value);
        var invalid = new HashSet<char>(Path.GetInvalidFileNameChars());
        var output = new StringBuilder();
        bool changed = false;
        foreach (char character in raw)
        {
            if (invalid.Contains(character) || Char.IsControl(character))
            {
                output.Append('_');
                changed = true;
            }
            else output.Append(character);
        }
        string result = output.ToString().TrimEnd(' ', '.');
        if (result != output.ToString()) changed = true;
        if (String.IsNullOrWhiteSpace(result)) result = "item";
        string stem = Path.GetFileNameWithoutExtension(result).ToUpperInvariant();
        string[] reserved = { "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9" };
        if (Array.IndexOf(reserved, stem) >= 0)
        {
            result = "_" + result;
            changed = true;
        }
        if (changed)
        {
            string extension = Path.GetExtension(result);
            string name = Path.GetFileNameWithoutExtension(result);
            result = name + "-" + ShortHash(raw) + extension;
        }
        return result.Length <= 180 ? result : result.Substring(0, 160) + "-" + ShortHash(raw) + Path.GetExtension(result);
    }

    private static string ShortHash(string value)
    {
        using (SHA256 hash = SHA256.Create())
        {
            byte[] bytes = hash.ComputeHash(Encoding.UTF8.GetBytes(value));
            return BitConverter.ToString(bytes, 0, 4).Replace("-", "").ToLowerInvariant();
        }
    }

    private static bool IsHex(string value, int length)
    {
        if (value == null || value.Length != length) return false;
        foreach (char character in value)
        {
            if (!Uri.IsHexDigit(character)) return false;
        }
        return true;
    }

    private static void EnsureInside(string root, string target)
    {
        string prefix = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        if (!target.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new DesktopException("unsafe_path", "A transfer path is unsafe.");
        }
    }

    private void CleanupExpired()
    {
        CleanupTree(Path.Combine(root, "leases"), TimeSpan.FromDays(7), true);
        CleanupTree(Path.Combine(root, "objects"), TimeSpan.FromDays(14), false);
    }

    private static void CleanupTree(string path, TimeSpan age, bool protectActive)
    {
        if (!Directory.Exists(path)) return;
        foreach (string directory in Directory.GetDirectories(path))
        {
            try
            {
                if (protectActive && File.Exists(Path.Combine(directory, ".active"))) continue;
                if (Directory.GetLastWriteTimeUtc(directory) < DateTime.UtcNow.Subtract(age))
                {
                    Directory.Delete(directory, true);
                }
            }
            catch { }
        }
    }
}

internal static class NativePhotoshop
{
    internal static string FindRequiredApplication()
    {
        foreach (var hive in new[] { Microsoft.Win32.Registry.CurrentUser, Microsoft.Win32.Registry.LocalMachine })
        {
            using (var key = hive.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe"))
            {
                string candidate = key == null ? "" : Convert.ToString(key.GetValue(""));
                if (!String.IsNullOrWhiteSpace(candidate) && File.Exists(candidate)) return Path.GetFullPath(candidate);
            }
        }
        foreach (string programFiles in new[] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86) })
        {
            string adobe = Path.Combine(programFiles,"Adobe");
            if (!Directory.Exists(adobe)) continue;
            foreach (string folder in Directory.GetDirectories(adobe,"Adobe Photoshop *").OrderByDescending(value => value))
            {
                string candidate = Path.Combine(folder,"Photoshop.exe");
                if (File.Exists(candidate)) return candidate;
            }
        }
        throw new DesktopException("photoshop_unavailable", "Adobe Photoshop is not installed or registered. Install Photoshop, restart Sports Cave OS Desktop, then retry.");
    }

    internal static ProcessStartInfo DefaultAppStartInfo(string target)
    {
        if (!File.Exists(target) || !String.Equals(Path.GetExtension(target), ".psd", StringComparison.OrdinalIgnoreCase))
            throw new DesktopException("master_required", "The verified PSD master is unavailable.");
        return new ProcessStartInfo(target) { UseShellExecute = true };
    }

    internal static ProcessStartInfo StartInfo(string executable, string target)
    {
        if (String.IsNullOrWhiteSpace(executable) || !File.Exists(executable) || !Path.GetFileName(executable).Equals("Photoshop.exe",StringComparison.OrdinalIgnoreCase))
            throw new DesktopException("photoshop_unavailable", "Adobe Photoshop is unavailable. Install or repair Photoshop, then retry.");
        if (!File.Exists(target) || !Path.GetExtension(target).Equals(".psd",StringComparison.OrdinalIgnoreCase))
            throw new DesktopException("master_not_synced", "The linked PSD master is unavailable. Check Dropbox sync, then retry.");
        return new ProcessStartInfo(executable) { Arguments = "\"" + target + "\"", UseShellExecute = false };
    }

    internal static async Task VerifyMasterAsync(string target, string root, long expectedSize, string expectedHash, CancellationToken cancellation)
    {
        try
        {
            using (var input = new FileStream(target,FileMode.Open,FileAccess.Read,FileShare.Read,128*1024,true))
            {
                var resolved = new StringBuilder(32768);
                uint length = NativeMethods.GetFinalPathNameByHandle(input.SafeFileHandle,resolved,(uint)resolved.Capacity,0);
                string actual = resolved.ToString();
                if (actual.StartsWith(@"\\?\UNC\")) actual = @"\\" + actual.Substring(8);
                else if (actual.StartsWith(@"\\?\")) actual = actual.Substring(4);
                string prefix = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                if (length == 0 || length >= resolved.Capacity || !actual.StartsWith(prefix,StringComparison.OrdinalIgnoreCase))
                    throw new DesktopException("master_scope_denied", "The synced master resolves outside the configured Dropbox folder.");
                // Reading the cloud placeholder requests Windows/Dropbox hydration, without writing the master.
                byte[] block = new byte[4*1024*1024];
                using (var hashes = new MemoryStream())
                using (var sha = SHA256.Create())
                {
                    int total;
                    while (true)
                    {
                        total = 0;
                        int amount;
                        while (total < block.Length && (amount = await input.ReadAsync(block,total,block.Length-total,cancellation)) > 0) total += amount;
                        if (total == 0) break;
                        byte[] hash = sha.ComputeHash(block,0,total);
                        hashes.Write(hash,0,hash.Length);
                    }
                    string actualHash = BitConverter.ToString(sha.ComputeHash(hashes.ToArray())).Replace("-","").ToLowerInvariant();
                    if (input.Length != expectedSize || !actualHash.Equals(expectedHash,StringComparison.OrdinalIgnoreCase))
                        throw new DesktopException("master_sync_pending", "Dropbox has not synced this exact master revision yet. Wait for Dropbox sync to complete, then retry Open PSD.");
                }
            }
        }
        catch (IOException) { throw new DesktopException("master_hydration_failed", "Dropbox could not make this master available. Check Dropbox Desktop is running, make the file available offline, then retry."); }
        catch (UnauthorizedAccessException) { throw new DesktopException("master_permission_denied", "Windows cannot read the linked master. Check local file permissions and Dropbox sync, then retry."); }
    }
}

internal static class NativePayload
{
    internal static System.Windows.DataObject Create(string[] paths)
    {
        if (paths == null || paths.Length == 0)
        {
            throw new DesktopException("empty_selection", "Select at least one item.");
        }
        foreach (string path in paths)
        {
            if (!File.Exists(path) && !Directory.Exists(path))
            {
                throw new DesktopException("cache_missing", "A prepared file is unavailable.");
            }
        }
        var data = new System.Windows.DataObject();
        data.SetData(System.Windows.DataFormats.FileDrop, paths);
        var effect = new MemoryStream(BitConverter.GetBytes(1U));
        data.SetData("Preferred DropEffect", effect, false);
        return data;
    }
}

internal sealed class DesktopException : Exception
{
    internal readonly string Code;
    internal DesktopException(string code, string message) : base(message) { Code = code; }
}

internal static class NativeMethods
{
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    internal static extern uint GetFinalPathNameByHandle(Microsoft.Win32.SafeHandles.SafeFileHandle handle, StringBuilder path, uint size, uint flags);

    [DllImport("user32.dll")]
    internal static extern short GetAsyncKeyState(int virtualKey);

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    internal static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateHardLink(
        string newFileName, string existingFileName, IntPtr securityAttributes);
}

internal static class DesktopLog
{
    private static readonly object Sync = new object();
    internal static void Write(string action, string status, string code, int items)
    {
        try
        {
            string folder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "SportsCaveOS", "Logs");
            Directory.CreateDirectory(folder);
            string line = DateTime.UtcNow.ToString("o")
                + " action=" + Safe(action)
                + " status=" + Safe(status)
                + " code=" + Safe(code)
                + " items=" + Math.Max(0, items) + Environment.NewLine;
            lock (Sync)
            {
                File.AppendAllText(Path.Combine(folder, "desktop.log"), line);
            }
        }
        catch { }
    }

    private static string Safe(string value)
    {
        string clean = Convert.ToString(value);
        return clean.Length > 80 ? clean.Substring(0, 80) : clean.Replace(" ", "_");
    }
}

// Additive OS chooser; existing helpers, caches and Photoshop code are untouched.
internal static class NativeFileOpening
{
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]
    internal struct OpenAsInfo { [MarshalAs(UnmanagedType.LPWStr)] public string File; [MarshalAs(UnmanagedType.LPWStr)] public string Class; public uint Flags; }
    [DllImport("shell32.dll",CharSet=CharSet.Unicode)]
    private static extern int SHOpenWithDialog(IntPtr owner,ref OpenAsInfo info);
    private static readonly HashSet<string> Blocked = new HashSet<string>(new[] { ".appref-ms",".application",".bat",".chm",".cmd",".com",".cpl",".dll",".exe",".gadget",".hta",".inf",".ins",".isp",".jar",".js",".jse",".lnk",".msc",".msi",".msp",".mst",".pif",".ps1",".py",".pyw",".reg",".scr",".sct",".shb",".shs",".url",".vbs",".vbe",".website",".ws",".wsc",".wsf" },StringComparer.OrdinalIgnoreCase);
    internal static void CheckType(string path)
    {
        if (Blocked.Contains(Path.GetExtension(path.TrimEnd(' ','.'))))
            throw new DesktopException("file_type_denied", "This file type cannot be opened by the desktop helper.");
    }
    internal static OpenAsInfo OptionsFor(string path)
    {
        if (!File.Exists(path) || Blocked.Contains(Path.GetExtension(path.TrimEnd(' ','.'))))
            throw new DesktopException("open_with_denied","This file cannot be opened with the application chooser.");
        return new OpenAsInfo { File=path,Class=null,Flags=4 }; // OAIF_EXEC only; never register/force defaults.
    }
    internal static ProcessStartInfo DefaultAppsInfo() { return new ProcessStartInfo("ms-settings:defaultapps") { UseShellExecute=true }; }
    internal static void OpenWith(string path,IntPtr owner)
    {
        OpenAsInfo info=OptionsFor(path);int result=SHOpenWithDialog(owner,ref info);
        if (result == unchecked((int)0x800704C7) || result == 1) throw new DesktopException("cancelled","Open With cancelled.");
        if (result < 0) throw new DesktopException("open_with_unavailable","Windows could not show Open With. Download the file or use Open With in File Explorer.");
    }
}

// Browser launch contains only a short-lived, account-bound one-use code; never paths or grant secrets.
internal static class BrowserFileLaunch
{
    internal static string Resolve(Uri uri, DesktopConfig config)
    {
        if (uri.Scheme != "sports-cave-files" || uri.Host != "launch" || uri.AbsolutePath != ""
            && uri.AbsolutePath != "/" || !String.IsNullOrEmpty(uri.UserInfo) || uri.Port != -1)
            throw new DesktopException("invalid_launch", "The desktop launch is invalid.");
        string query = uri.Query.TrimStart('?');
        if (!query.StartsWith("origin=",StringComparison.Ordinal) || query.IndexOf('&') >= 0)
            throw new DesktopException("invalid_launch", "The desktop launch is invalid.");
        string origin = Uri.UnescapeDataString(query.Substring(7));
        Uri source;
        if (!Uri.TryCreate(origin,UriKind.Absolute,out source) || !config.Allows(origin)
            || !String.IsNullOrEmpty(source.UserInfo) || source.AbsolutePath != "/"
            || !String.IsNullOrEmpty(source.Query) || !String.IsNullOrEmpty(source.Fragment)
            || !(source.Scheme == "https" || source.IsLoopback && source.Scheme == "http"))
            throw new DesktopException("launch_origin_denied", "This desktop launch origin is not authorised.");
        string code = uri.Fragment.TrimStart('#');
        if (!System.Text.RegularExpressions.Regex.IsMatch(code,"^[A-Za-z0-9_-]{43}$"))
            throw new DesktopException("invalid_launch", "The desktop launch is invalid or expired.");
        return source.GetLeftPart(UriPartial.Authority)+"/files-native-launch#"+code;
    }
}

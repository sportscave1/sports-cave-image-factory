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
using System.Windows.Media.Imaging;

[assembly: System.Reflection.AssemblyTitle("Sports Cave OS Desktop")]
[assembly: System.Reflection.AssemblyDescription("Persistent native Windows host for Sports Cave OS")]
[assembly: System.Reflection.AssemblyProduct("Sports Cave OS Desktop")]
[assembly: System.Reflection.AssemblyCompany("Sports Cave")]
[assembly: System.Reflection.AssemblyVersion("6.0.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("6.0.0.0")]

internal static class Program
{
    internal const int HelperVersion = 6;
    private const string MutexName = @"Local\SportsCaveOSDesktop-v6";
    private const string ShowEventName = @"Local\SportsCaveOSDesktop-Show-v6";
    private const string FilesEventName = @"Local\SportsCaveOSDesktop-Files-v6";

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
    private CoreWebView2Environment environment;
    private bool initialized;
    private bool redirectedForSignIn;
    private bool navigateFilesWhenReady;

    internal DesktopWindow(
        DesktopConfig desktopConfig, string requestedUrl = "", bool keepResident = true,
        CoreWebView2Environment sharedEnvironment = null)
    {
        config = desktopConfig;
        cache = new NativeCache(config.RootPath);
        environment = sharedEnvironment;
        initialUrl = String.IsNullOrWhiteSpace(requestedUrl)
            ? config.AppUrl : requestedUrl;
        persistent = keepResident;
        Title = "Sports Cave OS Desktop";
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

    private async void OnLoaded(object sender, RoutedEventArgs args)
    {
        await InitializeBrowser();
    }

    private async Task InitializeBrowser()
    {
        if (initialized) return;
        initialized = true;
        try
        {
            if (browser.CoreWebView2 == null)
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
                    try
                    {
                        bool blank = windowArgs.Uri.Equals(
                            "about:blank", StringComparison.OrdinalIgnoreCase);
                        if (blank || config.Allows(windowArgs.Uri))
                        {
                            var child = new DesktopWindow(
                                config, windowArgs.Uri, false, environment);
                            child.Show();
                            await child.InitializeBrowser();
                            windowArgs.NewWindow = child.browser.CoreWebView2;
                        }
                        windowArgs.Handled = true;
                    }
                    finally
                    {
                        deferral.Complete();
                    }
                };
                browser.CoreWebView2.Navigate(initialUrl);
                if (navigateFilesWhenReady)
                {
                    NavigateToFiles();
                }
            }
        }
        catch (Exception error)
        {
            DesktopLog.Write("webview", "failed", error.GetType().Name, 0);
            MessageBox.Show(
                "Sports Cave Desktop could not start WebView2. Reinstall the desktop helper.",
                "Sports Cave OS Desktop", MessageBoxButton.OK, MessageBoxImage.Error);
        }
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
        navigateFilesWhenReady = true;
        ShowAndFocus();
        if (browser.CoreWebView2 == null) return;
        Uri appUri = new Uri(config.AppUrl);
        browser.CoreWebView2.Navigate(
            appUri.GetLeftPart(UriPartial.Authority) + "/files-window");
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
                    { "capabilities", new[] { "drag", "copyFile", "copyImage", "openFile", "folders", "cancel" } },
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
            if (action != "drag" && action != "copyFile"
                && action != "copyImage" && action != "openFile")
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
                string[] paths = await cache.MaterializeAsync(
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
                else
                {
                    foreach (string path in paths)
                    {
                        Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
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
        var data = new System.Windows.DataObject();
        data.SetImage(bitmap);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        var png = new MemoryStream();
        encoder.Save(png);
        png.Position = 0;
        data.SetData("PNG", png, false);
        SetClipboardData(data);
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
    private readonly HttpClient client = new HttpClient();

    internal NativeCache(string configuredRoot = "")
    {
        string testRoot = Convert.ToString(
            Environment.GetEnvironmentVariable("SPORTS_CAVE_FILE_CACHE"));
        root = String.IsNullOrWhiteSpace(testRoot)
            ? Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "SportsCaveOS", "FileCache")
            : Path.GetFullPath(testRoot);
        localRoot = ResolveConfiguredRoot(configuredRoot);
        Directory.CreateDirectory(root);
        CleanupExpired();
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
    [DllImport("user32.dll")]
    internal static extern short GetAsyncKeyState(int virtualKey);

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

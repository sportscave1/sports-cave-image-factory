using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

[assembly: AssemblyTitle("Photoshop")]
[assembly: AssemblyDescription("Open in Photoshop")]
[assembly: AssemblyProduct("Photoshop")]
[assembly: AssemblyCompany("Sports Cave")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length != 1 || args[0].Length > 32768)
            {
                return 1;
            }

            Uri request;
            if (!Uri.TryCreate(args[0], UriKind.Absolute, out request)
                || !string.Equals(request.Scheme, "sports-cave-photoshop", StringComparison.OrdinalIgnoreCase)
                || !string.Equals(request.Host, "open", StringComparison.OrdinalIgnoreCase))
            {
                return 1;
            }

            string installRoot = AppDomain.CurrentDomain.BaseDirectory;
            string helperPath = Path.Combine(installRoot, "SportsCaveFilesHelper.ps1");
            string powershellPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.System),
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe"
            );
            if (!File.Exists(helperPath) || !File.Exists(powershellPath))
            {
                return 1;
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = powershellPath,
                Arguments = "-WindowStyle Hidden -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "
                    + QuoteArgument(helperPath) + " " + QuoteArgument(args[0]),
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            };
            Process.Start(startInfo);
            return 0;
        }
        catch
        {
            return 1;
        }
    }

    private static string QuoteArgument(string value)
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

// ParloSetup.exe: a one-file download that runs "Install Parlo.bat", which it carries
// inside itself. All the real work stays in that script and installer.ps1, so there
// is one install path to maintain. Built by installer/build-setup.ps1 with the C#
// compiler that is part of Windows (no extra tools).
//   ParloSetup.exe                      install
//   ParloSetup.exe --extract <folder>   only write the script there (for checking)
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

static class ParloSetup
{
    static int Main(string[] args)
    {
        try
        {
            bool extractOnly = args.Length == 2 && args[0] == "--extract";
            string folder = extractOnly ? args[1] : Path.Combine(Path.GetTempPath(), "ParloSetup-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(folder);
            string script = Path.Combine(folder, "Install Parlo.bat");
            using (Stream source = Assembly.GetExecutingAssembly().GetManifestResourceStream("InstallParlo.bat"))
            using (FileStream target = File.Create(script))
                source.CopyTo(target);
            if (extractOnly) return 0;

            var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe", "/c \"\"" + script + "\"\"");
            start.UseShellExecute = false; // keep one window, so messages from the script stay visible
            using (Process p = Process.Start(start))
            {
                p.WaitForExit();
                try { Directory.Delete(folder, true); } catch { /* a temporary folder; Windows clears it later */ }
                return p.ExitCode;
            }
        }
        catch (Exception e)
        {
            Console.WriteLine("Parlo setup could not start: " + e.Message);
            Console.WriteLine("Press Enter to close.");
            Console.ReadLine();
            return 1;
        }
    }
}

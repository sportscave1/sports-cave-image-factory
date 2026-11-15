using System;
using System.IO;
class NativeSaveAsChecks {
    static void Require(bool ok){if(!ok)throw new Exception("Save As guard failed");}
    static void Rejected(Action action){try{action();}catch{return;}throw new Exception("Unsafe destination accepted");}
    static int Main(){
        string folder=Path.Combine(Path.GetTempPath(),"recorder-save-as-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        string old=Environment.GetEnvironmentVariable("SC_RECORDER_DOWNLOAD_DIRECTORY");
        try {
            Environment.SetEnvironmentVariable("SC_RECORDER_DOWNLOAD_DIRECTORY",folder);
            string one=BrowserDownload.SaveAs.NewDestination(folder,"sample.txt");
            string two=BrowserDownload.SaveAs.NewDestination(folder,"sample.txt");
            Require(one!=two&&Path.GetDirectoryName(one)==folder&&Path.GetExtension(one)==".txt");
            Require(!File.Exists(one)&&!File.Exists(two));
            var direct=new BrowserDownload.SaveAs(IntPtr.Zero,folder,"sample.txt");
            Require(direct.MatchesVerifiedResult(Path.Combine(folder,"sample.txt")));
            Require(direct.MatchesVerifiedResult(Path.Combine(folder,"sample (31).txt")));
            Require(!direct.MatchesVerifiedResult(Path.Combine(folder,"sample-old.txt")));
            Require(!direct.MatchesVerifiedResult(Path.Combine(folder,"sample (0).txt")));
            Require(!direct.MatchesVerifiedResult(Path.Combine(folder,"sample (31).exe")));
            Require(!direct.MatchesVerifiedResult(Path.Combine(Path.GetTempPath(),"sample.txt")));
            string selected=BrowserDownload.SaveAs.SuggestedDestination(folder,"sample.txt","sample (32)");
            Require(selected==Path.Combine(folder,"sample (32).txt"));
            Require(BrowserDownload.SaveAs.SuggestedDestination(folder,"sample.txt","sample.txt")==Path.Combine(folder,"sample.txt"));
            Rejected(()=>BrowserDownload.SaveAs.SuggestedDestination(folder,"sample.txt","../sample.txt"));
            Rejected(()=>BrowserDownload.SaveAs.SuggestedDestination(folder,"sample.txt","sample-old.txt"));
            Rejected(()=>BrowserDownload.SaveAs.SuggestedDestination(folder,"sample.txt","sample (0).txt"));
            Rejected(()=>BrowserDownload.SaveAs.SuggestedDestination(folder,"sample.txt","sample.exe"));
            File.WriteAllText(Path.Combine(folder,"sample (5).txt"),"older preserved file");
            Rejected(()=>BrowserDownload.SaveAs.SuggestedDestination(folder,"sample.txt","sample (5).txt"));
            Require(File.ReadAllText(Path.Combine(folder,"sample (5).txt"))=="older preserved file");
            File.Delete(Path.Combine(folder,"sample (5).txt"));
            typeof(BrowserDownload.SaveAs).GetField("destination",System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Instance).SetValue(direct,selected);
            typeof(BrowserDownload.SaveAs).GetField("invoked",System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Instance).SetValue(direct,true);
            Require(direct.MatchesVerifiedResult(direct.Destination));
            Require(!direct.MatchesVerifiedResult(Path.Combine(folder,"sample (31).txt")));

            Rejected(()=>BrowserDownload.SaveAs.NewDestination(folder,"../older.txt"));
            Rejected(()=>BrowserDownload.SaveAs.NewDestination(folder,"bad:name.txt"));
            Rejected(()=>BrowserDownload.SaveAs.NewDestination(Path.GetTempPath(),"sample.txt"));
            Require(!BrowserDownload.OwnedSaveDialog(IntPtr.Zero,IntPtr.Zero));
            var normal=new BrowserDownload.WaitBudget();
            Require(!normal.Expired(29999,false)&&normal.Expired(30000,false));
            var choice=new BrowserDownload.WaitBudget();
            Require(!choice.Expired(1000,true)&&!choice.Expired(120000,true));
            Require(!choice.Expired(120001,false)&&!choice.Expired(150000,false)&&choice.Expired(150001,false));
            Require(choice.Expired(150001,true)); // Reopening cannot renew it.
            var abandoned=new BrowserDownload.WaitBudget();
            Require(!abandoned.Expired(299999,true)&&abandoned.Expired(300000,true));
            var lateClose=new BrowserDownload.WaitBudget();
            Require(!lateClose.Expired(299999,true)&&!lateClose.Expired(300000,false)&&lateClose.Expired(330000,false));
            Console.WriteLine("PASS 28 offline Save As destination/ownership/deadline guards; no desktop input.");return 0;
        } finally {Environment.SetEnvironmentVariable("SC_RECORDER_DOWNLOAD_DIRECTORY",old);Directory.Delete(folder);}
    }
}

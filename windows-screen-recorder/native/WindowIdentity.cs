using System;
using System.IO;
using System.Text.RegularExpressions;

// Evidence from Windows' move/resize-start event, correlated to one physical
// mouse gesture. A changed rectangle or an arbitrary drag is not sufficient.
sealed class WindowMoveGesture {
    readonly object gate=new object();
    IntPtr window;int epoch;uint started;bool observed;
    public void Begin(IntPtr owner,int generation,uint time) {
        lock(gate){window=owner;epoch=generation;started=time;observed=false;}
    }
    public bool Observe(IntPtr owner,int generation,uint time) {
        lock(gate){
            if(owner==IntPtr.Zero||owner!=window||generation!=epoch||unchecked(time-started)>1500)return false;
            observed=true;return true;
        }
    }
    public bool Matches(IntPtr owner,int generation) {
        lock(gate)return observed&&owner!=IntPtr.Zero&&owner==window&&generation==epoch;
    }
}

static class WindowIdentity {
    // Page projections share the same protocol in Chrome and Edge. This is
    // process eligibility only: page/profile, scope and origin checks still apply.
    public static bool ChromiumApp(string app) {
        if(String.IsNullOrEmpty(app))return false;
        string name=Path.GetFileName(app);
        return String.Equals(name,"msedge.exe",StringComparison.OrdinalIgnoreCase)||
            String.Equals(name,"chrome.exe",StringComparison.OrdinalIgnoreCase);
    }
    // Child windows resolve to their top-level root. Owned popups may resolve
    // to the same-process owner, but never cross an application boundary.
    public static IntPtr Root(IntPtr root,IntPtr owner,uint rootPid,uint ownerPid) {
        return owner!=IntPtr.Zero&&ownerPid==rootPid?owner:root;
    }
    public static bool InitialMatches(IntPtr prepared,IntPtr actual) {
        return prepared==IntPtr.Zero||prepared==actual;
    }
    public static bool IsToolbar(uint inputPid,uint hostPid) {return inputPid==hostPid;}
    public static bool EdgeTitle(string title,out string page,out string profile) {
        page=profile=null;
        if(String.IsNullOrEmpty(title)||title.Length>256||title.IndexOfAny(new[]{'\r','\n'})>=0)return false;
        string suffix=title.EndsWith(" - Microsoft\u200b Edge",StringComparison.Ordinal)?" - Microsoft\u200b Edge":
                      title.EndsWith(" - Microsoft Edge",StringComparison.Ordinal)?" - Microsoft Edge":null;
        if(suffix==null)return false;
        string body=title.Substring(0,title.Length-suffix.Length);
        int separator=body.LastIndexOf(" - ",StringComparison.Ordinal);
        if(separator<=0||separator+3==body.Length)return false;
        profile=body.Substring(separator)+suffix;
        page=body.Substring(0,separator);
        var count=Regex.Match(page,@" and (?:1 more page|[2-9] more pages|[1-9][0-9]{1,3} more pages)$",RegexOptions.CultureInvariant);
        if(count.Success)page=page.Substring(0,count.Index);
        return page.Length>0;
    }
    public static bool EdgeTabNameMatches(string page,string name) {
        if(String.IsNullOrEmpty(page)||String.IsNullOrEmpty(name))return false;
        if(page==name)return true;
        if(!name.StartsWith(page,StringComparison.Ordinal))return false;
        string decoration=name.Substring(page.Length);
        return Regex.IsMatch(decoration,@"^ - Memory usage - [0-9]+(?:\.[0-9]+)? (?:KB|MB|GB)\z",RegexOptions.CultureInvariant)||
            Regex.IsMatch(decoration,@"^ - Part of tab group [^\r\n]{1,180}\z",RegexOptions.CultureInvariant);
    }
    public static bool PlaybackTitleMatches(string app,string recorded,string current,Func<string,bool> documentMatches) {
        if(String.Equals(recorded,current,StringComparison.Ordinal))return true;
        if(String.Equals(Path.GetFileName(app),"notepad.exe",StringComparison.OrdinalIgnoreCase)&&
            recorded.EndsWith(".txt - Notepad",StringComparison.OrdinalIgnoreCase)&&current.EndsWith(".txt - Notepad",StringComparison.OrdinalIgnoreCase)&&
            recorded.TrimStart('*')==current.TrimStart('*'))return true;
        if(!String.Equals(Path.GetFileName(app),"msedge.exe",StringComparison.OrdinalIgnoreCase))return false;
        string recordedPage,recordedProfile,currentPage,currentProfile;
        if(!EdgeTitle(recorded,out recordedPage,out recordedProfile)||!EdgeTitle(current,out currentPage,out currentProfile)||
           recordedPage!=currentPage||recordedProfile!=currentProfile)return false;
        // Tab-count decoration alone is insufficient. The same top-level
        // accessible document must independently identify the active page.
        return documentMatches(recordedPage);
    }
}

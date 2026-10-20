using System;
using System.IO;
using System.Text.RegularExpressions;

static class WindowIdentity {
    // Child windows resolve to their top-level root. Owned popups may resolve
    // to the same-process owner, but never cross an application boundary.
    public static IntPtr Root(IntPtr root,IntPtr owner,uint rootPid,uint ownerPid) {
        return owner!=IntPtr.Zero&&ownerPid==rootPid?owner:root;
    }
    public static bool InitialMatches(IntPtr prepared,IntPtr actual) {
        return prepared==IntPtr.Zero||prepared==actual;
    }
    public static bool IsToolbar(uint inputPid,uint hostPid) {return inputPid==hostPid;}
    static bool EdgeTitle(string title,out string page,out string profile) {
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
    public static bool PlaybackTitleMatches(string app,string recorded,string current,Func<string,bool> documentMatches) {
        if(String.Equals(recorded,current,StringComparison.Ordinal))return true;
        if(!String.Equals(Path.GetFileName(app),"msedge.exe",StringComparison.OrdinalIgnoreCase))return false;
        string recordedPage,recordedProfile,currentPage,currentProfile;
        if(!EdgeTitle(recorded,out recordedPage,out recordedProfile)||!EdgeTitle(current,out currentPage,out currentProfile)||
           recordedPage!=currentPage||recordedProfile!=currentProfile)return false;
        // Tab-count decoration alone is insufficient. The same top-level
        // accessible document must independently identify the active page.
        return documentMatches(recordedPage);
    }
}

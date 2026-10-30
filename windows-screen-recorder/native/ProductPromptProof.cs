using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;

// A bounded digest of the complete application-owned prompt, never a text
// editor selection. Clipboard contents are read only for this explicit Copy.
static class ProductPromptProof {
    public const string Prefix="Sports Cave prompt v1: ";
    public const int MaxBytes=1024*1024;
    public static Dictionary<string,object> Parse(string help) {
        foreach(string line in (help??"").Split('\n'))if(line.StartsWith(Prefix,StringComparison.Ordinal)) {
            if(line.Length>400)throw new Exception("Prompt proof exceeded its bound.");
            var proof=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(line.Substring(Prefix.Length));
            if(proof.Count!=3||!proof.ContainsKey("sha256")||!proof.ContainsKey("utf16_length")||!proof.ContainsKey("utf8_length")||
                !(proof["sha256"] is string)||!Regex.IsMatch((string)proof["sha256"],"^[a-f0-9]{64}$")||
                !(proof["utf16_length"] is int)||!(proof["utf8_length"] is int)||
                (int)proof["utf16_length"]<1||(int)proof["utf8_length"]<1||
                (int)proof["utf16_length"]>MaxBytes||(int)proof["utf8_length"]>MaxBytes)
                throw new Exception("Invalid complete-prompt proof.");
            return proof;
        }
        return null;
    }
    public static bool Same(Dictionary<string,object> a,Dictionary<string,object> b) {
        return a!=null&&b!=null&&Equals(a["sha256"],b["sha256"])&&
            Equals(a["utf16_length"],b["utf16_length"])&&Equals(a["utf8_length"],b["utf8_length"]);
    }
    public static bool Matches(string text,Dictionary<string,object> proof) {
        if(text==null||text.Length>2*MaxBytes)return false;
        // Chromium's Windows clipboard transport expands LF to CRLF. Keep
        // exact compatibility for existing proofs, then verify the complete
        // payload with only that transport conversion reversed. No trimming,
        // truncation, lone-CR removal or Unicode normalization is permitted.
        return Exact(text,proof)||Exact(text.Replace("\r\n","\n"),proof);
    }
    static bool Exact(string text,Dictionary<string,object> proof) {
        return proof!=null&&text!=null&&text.Length==Convert.ToInt32(proof["utf16_length"])&&
            Encoding.UTF8.GetByteCount(text)==Convert.ToInt32(proof["utf8_length"])&&CopyText.Hash(text)==(string)proof["sha256"];
    }
    public static bool ClipboardMatches(Dictionary<string,object> proof) {
        return (bool)Application.Current.Dispatcher.Invoke(new Func<bool>(()=>Matches(Clipboard.GetText(TextDataFormat.UnicodeText),proof)));
    }
}

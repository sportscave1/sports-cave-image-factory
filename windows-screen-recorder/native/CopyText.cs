using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Windows;
using System.Windows.Automation;

// Explicit plain-text copy only. Never polls the clipboard or reads an
// unclassified document. A changed source requires a fresh recording.
static class CopyText {
    public static string Hash(string value) {
        using(var hash=SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value))).Replace("-","").ToLowerInvariant();
    }
    public static bool Matches(string source,string selected,string hash) {
        return source!=null&&source.Length<=2000&&!String.IsNullOrEmpty(selected)&&selected.Length<=2000&&
            source.IndexOf(selected,StringComparison.Ordinal)>=0&&Hash(source)==hash;
    }
    public static string ReadSource(AutomationElement element) {
        object privacy=element.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true);
        if(!(privacy is bool)||(bool)privacy||!element.Current.IsEnabled||
            element.Current.AutomationId=="RootWebArea"||
            (element.Current.ControlType!=ControlType.Edit&&element.Current.ControlType!=ControlType.Document))
            throw new Exception("Copy needs a classified text editor. Page-wide copy is not supported yet.");
        Capture.Safe(element.Current.Name);Capture.Safe(element.Current.AutomationId);
        object pattern;
        if(!element.TryGetCurrentPattern(TextPattern.Pattern,out pattern))
            throw new Exception("This editor does not expose a verifiable text selection.");
        string source=((TextPattern)pattern).DocumentRange.GetText(2001);
        if(source.Length>2000)throw new Exception("Copy source exceeds the supported text size.");
        return Capture.Safe(source);
    }
    public static Dictionary<string,object> Observe(AutomationElement element) {
        string source=ReadSource(element);object pattern;
        element.TryGetCurrentPattern(TextPattern.Pattern,out pattern);
        var ranges=((TextPattern)pattern).GetSelection();
        if(ranges.Length!=1)throw new Exception("Copy requires exactly one text selection.");
        string selected=Capture.Safe(ranges[0].GetText(2001));
        string hash=Hash(source);
        if(!Matches(source,selected,hash))throw new Exception("Copy selection is empty or outside its bounded source.");
        // Inspect clipboard only after validating the explicit Ctrl+C source.
        string actual=(string)Application.Current.Dispatcher.Invoke(new Func<string>(()=>Clipboard.GetText(TextDataFormat.UnicodeText)));
        if(actual!=selected)throw new Exception("Copy result does not match the selected text. Draft preserved.");
        if(ReadSource(element)!=source)throw new Exception("Copy source changed during observation.");
        return new Dictionary<string,object>{{"text",selected},{"source_sha256",hash}};
    }
    public static void ValidateSource(AutomationElement element,Dictionary<string,object> value) {
        if(!Matches(ReadSource(element),(string)value["text"],(string)value["source_sha256"]))
            throw new Exception("The copy source changed. Clipboard was not replaced; record the changed workflow again.");
    }
    public static bool Apply(Dictionary<string,object> value,Action check) {
        return (bool)Application.Current.Dispatcher.Invoke(new Func<bool>(()=>{
            check();string text=(string)value["text"];
            Clipboard.SetText(text,TextDataFormat.UnicodeText);
            return Clipboard.GetText(TextDataFormat.UnicodeText)==text;
        }));
    }
}

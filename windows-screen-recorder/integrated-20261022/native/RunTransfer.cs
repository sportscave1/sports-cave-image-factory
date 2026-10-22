using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows;
using System.Windows.Automation;

// Run memory only: values never enter action JSON, journal results or diagnostics.
sealed class RunTransfer {
    [DllImport("user32.dll")] static extern uint GetClipboardSequenceNumber();
    string value;int slot=-1;uint sequence;
    public void Clear(){value=null;slot=-1;sequence=0;}
    public static string Bounded(string text) {
        if(String.IsNullOrEmpty(text)||text.Length>1048576||Encoding.UTF8.GetByteCount(text)>1048576)
            throw new Exception("Transfer is empty or exceeds 1 MiB. Nothing was substituted.");
        return text;
    }
    public static string ReadEditor(AutomationElement e,bool fullSelection) {
        object password=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true),pattern;
        if(!(password is bool)||(bool)password||!e.Current.IsEnabled||e.Current.AutomationId=="RootWebArea"||
            (e.Current.ControlType!=ControlType.Edit&&e.Current.ControlType!=ControlType.Document))
            throw new Exception("Transfer requires a classified, non-secure text field.");
        Capture.Safe(e.Current.Name);Capture.Safe(e.Current.AutomationId);
        string text;
        if(fullSelection) {
            if(!e.TryGetCurrentPattern(TextPattern.Pattern,out pattern))throw new Exception("Copy selection is not observable.");
            var source=(TextPattern)pattern;var ranges=source.GetSelection();
            text=Bounded(source.DocumentRange.GetText(1048577));
            if(ranges.Length!=1||ranges[0].GetText(1048577)!=text)
                throw new Exception("Dynamic selection Copy currently requires the complete text field selected. Draft preserved.");
        } else if(e.TryGetCurrentPattern(ValuePattern.Pattern,out pattern))text=Bounded(((ValuePattern)pattern).Current.Value);
        else if(e.TryGetCurrentPattern(TextPattern.Pattern,out pattern))text=Bounded(((TextPattern)pattern).DocumentRange.GetText(1048577));
        else throw new Exception("Transfer field has no readable text pattern.");
        return text;
    }
    public static string ClipboardText() {
        return (string)Application.Current.Dispatcher.Invoke(new Func<string>(()=>Clipboard.GetText(TextDataFormat.UnicodeText)));
    }
    public void Observe(int id,string expected) {
        Clear();expected=Bounded(expected);
        uint before=GetClipboardSequenceNumber();
        if(ClipboardText()!=expected||before!=GetClipboardSequenceNumber())throw new Exception("Copy result changed or could not be verified. No transfer retained.");
        value=expected;slot=id;sequence=before;
    }
    public void Copy(int id,string source,Action check) {
        Clear();source=Bounded(source);
        Application.Current.Dispatcher.Invoke(new Action(()=>{check();Clipboard.SetText(source,TextDataFormat.UnicodeText);}));
        check();Observe(id,source);
    }
    public string Get(int id) {
        if(id!=slot||value==null)throw new Exception("This run has no verified Copy for the Paste. Clipboard was not substituted.");
        if(sequence!=GetClipboardSequenceNumber()||ClipboardText()!=value||sequence!=GetClipboardSequenceNumber()) {Clear();throw new Exception("Clipboard changed after Copy. Paste stopped.");}
        return value;
    }
}

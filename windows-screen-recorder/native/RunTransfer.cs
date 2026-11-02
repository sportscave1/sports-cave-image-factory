using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows;
using System.Windows.Automation;

// Run memory only: values never enter action JSON, journal results or diagnostics.
sealed class RunTransfer {
    [DllImport("user32.dll")] static extern uint GetClipboardSequenceNumber();
    string value;int slot=-1;uint sequence;
    public void Clear(){value=null;slot=-1;sequence=0;}
    public void BeginCapture(bool resume) {
        // A pause belongs to the same draft. Get still verifies the Windows
        // clipboard sequence and complete value before allowing a later Paste.
        // A new recording must never inherit the previous draft's Copy.
        if(!resume)Clear();
    }
    public static string Bounded(string text) {
        if(String.IsNullOrEmpty(text)||text.Length>1048576||Encoding.UTF8.GetByteCount(text)>1048576)
            throw new Exception("Transfer is empty or exceeds 1 MiB. Nothing was substituted.");
        return text;
    }
    public static bool NativeDocument(Dictionary<string,object> target) {
        return !target.ContainsKey("browser")&&Equals(target["control_type"],"Document");
    }
    static string EditorLines(string text,bool nativeDocument) {
        // Native RichEdit document providers expose paragraph separators as CR,
        // while their clipboard/files use CRLF. Preserve every separator and
        // character; do not trim. Browser fields keep their stricter contract.
        return nativeDocument&&text!=null?text.Replace("\r\n","\n").Replace("\r","\n"):text;
    }
    public static string EditorValue(Func<string> readValue,Func<string> readDocument,bool nativeDocument=false,bool observeEmpty=false) {
        // Chromium exposes an empty edit's label through TextPattern, while
        // ValuePattern can truncate a long value. Reject an empty/failed value
        // read; for nonempty edits reconcile both providers before choosing the
        // complete text. Never accept unrelated label/document contents.
        if(readValue!=null) {
            string observed=readValue();
            // Result verification may see the old empty field while a large
            // semantic Paste is being published. Return only the observed empty
            // value, never its accessible label. Copy retains strict rejection.
            if(observeEmpty&&observed=="")return "";
            string value=EditorLines(Bounded(observed),nativeDocument);
            if(readDocument==null)return value;
            string document=EditorLines(Bounded(readDocument()),nativeDocument);
            string normalizedValue=value.Replace("\r\n","\n"),normalizedDocument=document.Replace("\r\n","\n");
            if(normalizedDocument.StartsWith(normalizedValue,StringComparison.Ordinal))return document;
            if(normalizedValue.StartsWith(normalizedDocument,StringComparison.Ordinal))return value;
            throw new Exception("Text providers disagree about the Copy source. Nothing was substituted.");
        }
        if(readDocument!=null)return EditorLines(Bounded(readDocument()),nativeDocument);
        throw new Exception("Transfer field has no readable text pattern.");
    }
    public static string ReadEditor(AutomationElement e,bool fullSelection,bool nativeDocument=false,bool observeEmpty=false) {
        object password=e.GetCurrentPropertyValue(AutomationElement.IsPasswordProperty,true),valuePattern,textPattern;
        if(!(password is bool)||(bool)password||!e.Current.IsEnabled||e.Current.AutomationId=="RootWebArea"||
            (e.Current.ControlType!=ControlType.Edit&&e.Current.ControlType!=ControlType.Document))
            throw new Exception("Transfer requires a classified, non-secure text field.");
        Capture.Safe(e.Current.Name);Capture.Safe(e.Current.AutomationId);
        e.TryGetCurrentPattern(ValuePattern.Pattern,out valuePattern);
        e.TryGetCurrentPattern(TextPattern.Pattern,out textPattern);
        var field=valuePattern as ValuePattern;var document=textPattern as TextPattern;
        string text=EditorValue(field==null?null:new Func<string>(()=>field.Current.Value),
            document==null?null:new Func<string>(()=>document.DocumentRange.GetText(1048577)),nativeDocument,observeEmpty);
        if(fullSelection) {
            if(document==null)throw new Exception("Copy selection is not observable.");
            var ranges=document.GetSelection();
            if(ranges.Length!=1||!SameEditorText(EditorLines(ranges[0].GetText(1048577),nativeDocument),text))
                throw new Exception("Dynamic selection Copy currently requires the complete text field selected. Draft preserved.");
        }
        return text;
    }
    public static string ClipboardText() {
        var dispatcher=Application.Current.Dispatcher;
        return ReadClipboardWithRetry(
            ()=> (string)dispatcher.Invoke(new Func<string>(()=>Clipboard.GetText(TextDataFormat.UnicodeText))),
            ()=>Thread.Sleep(20),!dispatcher.CheckAccess());
    }
    public static string ReadClipboardWithRetry(Func<string> read,Action wait,bool mayWait) {
        // The target can briefly own the clipboard while handling Ctrl+V.
        // Retry only this read, never the input or an uncertain application action.
        // Production waits run on the capture/playback worker, not the toolbar.
        for(int attempt=0;;attempt++) {
            try{return read();}
            catch(Exception error) {
                if(!ClipboardBusy(error))throw;
                if(!mayWait||attempt==7)throw new Exception("Clipboard is busy. Stop and preserve the draft; nothing was substituted.",error);
                wait();
            }
        }
    }
    static bool ClipboardBusy(Exception error) {
        // Dispatcher.Invoke can wrap the original clipboard exception.
        while(error is System.Reflection.TargetInvocationException&&error.InnerException!=null)
            error=error.InnerException;
        return error is ExternalException&&error.HResult==unchecked((int)0x800401D0);
    }
    public static void CopyWithReadback(Action write,Action verify,Func<uint> sequence,Action check) {
        uint before=sequence();bool openFailed=false;
        check();
        try {write();}
        catch(Exception error) {
            if(!ClipboardBusy(error))throw;
            // OleSetClipboard may succeed before clipboard persistence fails.
            // Never issue the write again. Only independent complete readback
            // and a new sequence can prove this attempt supplied the value.
            openFailed=true;
        }
        check();verify();check();
        if(openFailed&&sequence()==before)
            throw new Exception("Clipboard was busy and this Copy could not be confirmed. No transfer retained.");
    }
    public static bool SameEditorText(string left,string right) {
        return left!=null&&right!=null&&left.Replace("\r\n","\n")==right.Replace("\r\n","\n");
    }
    public void ObserveEditor(int id,string expected) {
        Clear();expected=Bounded(expected);
        uint before=GetClipboardSequenceNumber();
        string copied=ClipboardText();
        if(!SameEditorText(copied,expected)||before!=GetClipboardSequenceNumber())
            throw new Exception("Copy result changed or could not be verified. No transfer retained.");
        // Retain the actual Windows value, not a normalized reconstruction.
        value=Bounded(copied);slot=id;sequence=before;
    }
    public void Observe(int id,string expected) {
        Clear();expected=Bounded(expected);
        uint before=GetClipboardSequenceNumber();
        if(ClipboardText()!=expected||before!=GetClipboardSequenceNumber())throw new Exception("Copy result changed or could not be verified. No transfer retained.");
        value=expected;slot=id;sequence=before;
    }
    public void Copy(int id,string source,Action check) {
        Clear();source=Bounded(source);
        try {
            CopyWithReadback(
                ()=>Application.Current.Dispatcher.Invoke(new Action(()=>{check();Clipboard.SetText(source,TextDataFormat.UnicodeText);})),
                ()=>Observe(id,source),()=>GetClipboardSequenceNumber(),check);
        } catch {Clear();throw;}
    }
    public string Get(int id) {
        if(id!=slot||value==null)throw new Exception("This run has no verified Copy for the Paste. Clipboard was not substituted.");
        if(sequence!=GetClipboardSequenceNumber()||ClipboardText()!=value||sequence!=GetClipboardSequenceNumber()) {Clear();throw new Exception("Clipboard changed after Copy. Paste stopped.");}
        return value;
    }
}

using System;
using System.Runtime.InteropServices;
using System.Windows;

// No desktop targets or input hooks: exercise the production transfer value
// guard, preserving the clipboard and logging only the check count.
class RunTransferChecks {
    [DllImport("user32.dll")] static extern uint GetClipboardSequenceNumber();
    static void SetClipboardVerified(string text) {
        RunTransfer.CopyWithReadback(()=>Clipboard.SetText(text,TextDataFormat.UnicodeText),()=>{
            string actual=RunTransfer.ReadClipboardWithRetry(()=>Clipboard.GetText(TextDataFormat.UnicodeText),()=>System.Threading.Thread.Sleep(20),true);
            if(actual!=text)throw new Exception("Test clipboard write did not preserve complete content.");
        },()=>GetClipboardSequenceNumber(),()=>{});
    }
    static int checks;
    static void Require(bool value) { checks++; if(!value)throw new Exception("Transfer regression check failed: "+checks); }
    static void Reject(Action action,string reason) {
        try {action();} catch(Exception error){Require(error.Message.Contains(reason));return;}
        throw new Exception("Expected transfer rejection: "+reason);
    }
    [STAThread] static int Main() {
        var app=new Application();
        string previous=Clipboard.GetText(TextDataFormat.UnicodeText);
        try {
            int reads=0,waits=0;
            Require(RunTransfer.ReadClipboardWithRetry(()=>{if(++reads<3)throw new COMException("busy",unchecked((int)0x800401D0));return "complete";},()=>waits++,true)=="complete");
            Require(reads==3&&waits==2);
            reads=waits=0;
            Reject(()=>RunTransfer.ReadClipboardWithRetry(()=>{reads++;throw new COMException("busy",unchecked((int)0x800401D0));},()=>waits++,true),"Clipboard is busy");
            Require(reads==8&&waits==7);
            reads=waits=0;
            Reject(()=>RunTransfer.ReadClipboardWithRetry(()=>{reads++;throw new COMException("busy",unchecked((int)0x800401D0));},()=>waits++,false),"Clipboard is busy");
            Require(reads==1&&waits==0); // Never block the UI thread waiting.
            Reject(()=>RunTransfer.ReadClipboardWithRetry(()=>{throw new COMException("unrelated provider error",unchecked((int)0x80004005));},()=>{throw new Exception("must not retry");},true),"unrelated provider error");
            reads=waits=0;
            Require(RunTransfer.ReadClipboardWithRetry(()=>{if(++reads<3)throw new System.Reflection.TargetInvocationException(new COMException("busy",unchecked((int)0x800401D0)));return "complete";},()=>waits++,true)=="complete");
            Require(reads==3&&waits==2);
            int writes=0,verified=0;uint sequence=10;
            RunTransfer.CopyWithReadback(()=>{writes++;sequence++;throw new COMException("busy after write",unchecked((int)0x800401D0));},()=>verified++,()=>sequence,()=>{});
            Require(writes==1&&verified==1); // Readback, never another write.
            writes=verified=0;
            Reject(()=>RunTransfer.CopyWithReadback(()=>{writes++;throw new COMException("busy before write",unchecked((int)0x800401D0));},()=>verified++,()=>sequence,()=>{}),"could not be confirmed");
            Require(writes==1&&verified==1); // An equal stale value is insufficient.
            writes=0;
            Reject(()=>RunTransfer.CopyWithReadback(()=>{writes++;sequence++;throw new COMException("busy",unchecked((int)0x800401D0));},()=>{throw new Exception("complete value differs");},()=>sequence,()=>{}),"complete value differs");
            Require(writes==1);
            writes=0;
            Reject(()=>RunTransfer.CopyWithReadback(()=>{writes++;},()=>{},()=>sequence,()=>{throw new OperationCanceledException("Stop requested");}),"Stop requested");
            Require(writes==0);
            bool documentRead=false;
            Reject(()=>RunTransfer.EditorValue(()=>"",()=>{documentRead=true;return "Source text";}),"Transfer is empty");
            Require(!documentRead); // An empty edit's label must never become data.
            Require(RunTransfer.EditorValue(()=>"",()=>{documentRead=true;return "Source text";},false,true)=="");
            Require(!documentRead); // Verification observes emptiness without treating a label as content.
            Reject(()=>RunTransfer.EditorValue(()=>new string('x',1048577),null,false,true),"exceeds 1 MiB");
            Reject(()=>RunTransfer.EditorValue(()=>{throw new Exception("provider failed");},()=>"Source text"),"provider failed");
            Reject(()=>RunTransfer.EditorValue(()=>"actual value",()=>"accessible label"),"Text providers disagree");
            Require(RunTransfer.EditorValue(()=>"actual value",null)=="actual value");
            Require(RunTransfer.EditorValue(null,()=>"native document text")=="native document text");
            Reject(()=>RunTransfer.EditorValue(null,null),"no readable text pattern");
            Require(RunTransfer.SameEditorText("a\r\nb","a\nb"));
            Require(!RunTransfer.SameEditorText("a\rb","a\nb"));
            Require(!RunTransfer.SameEditorText("a\nb","a\nb\n"));
            Require(!RunTransfer.SameEditorText("a\nb","a\nc"));
            Require(RunTransfer.EditorValue(()=>"a\r\nb",()=>"a\rb",true)=="a\nb");
            Require(RunTransfer.EditorValue(null,()=>"\ra\r\rb\r",true)=="\na\n\nb\n");
            Require(!RunTransfer.SameEditorText(RunTransfer.EditorValue(null,()=>"a\r\rb",true),"a\nb"));
            Require(!RunTransfer.SameEditorText(RunTransfer.EditorValue(null,()=>"a\rc",true),"a\nb"));
            Require(RunTransfer.EditorValue(null,()=>"a\rb")=="a\rb"); // Browser contract unchanged.
            Require(RunTransfer.NativeDocument(new System.Collections.Generic.Dictionary<string,object>{{"control_type","Document"}}));
            Require(!RunTransfer.NativeDocument(new System.Collections.Generic.Dictionary<string,object>{{"control_type","Document"},{"browser",new object()}}));
            Require(!RunTransfer.NativeDocument(new System.Collections.Generic.Dictionary<string,object>{{"control_type","Edit"}}));
            string source=new string('x',126148)+"\nUnicode \u65e5\u672c\u8a9e \ud83c\udfc6\nend";
            string windows=source.Replace("\n","\r\n");
            Require(RunTransfer.EditorValue(()=>source.Substring(0,7881),()=>source)==source);
            Require(RunTransfer.EditorValue(()=>source,()=>source.Substring(0,7881))==source);
            Require(RunTransfer.EditorValue(()=>windows.Substring(0,7881),()=>source)==source);
            Require(RunTransfer.EditorValue(()=>windows,()=>source)==source);
            SetClipboardVerified(windows);
            var transfer=new RunTransfer();transfer.ObserveEditor(0,source);
            Require(transfer.Get(0)==windows);
            transfer.BeginCapture(true);
            Require(transfer.Get(0)==windows); // Same draft's Copy survives Pause/Resume.
            SetClipboardVerified("Unrelated replacement");
            transfer.BeginCapture(true); // Paused clipboard changes still invalidate Paste.
            bool rejected=false;try{transfer.Get(0);}catch{rejected=true;}Require(rejected);
            rejected=false;try{transfer.ObserveEditor(1,source);}catch{rejected=true;}Require(rejected);
            rejected=false;try{transfer.Get(1);}catch{rejected=true;}Require(rejected);
            SetClipboardVerified(windows);transfer.ObserveEditor(2,source);
            transfer.BeginCapture(false);
            Reject(()=>transfer.Get(2),"no verified Copy"); // A new draft cannot inherit it.
            Console.WriteLine(checks+" transfer checks passed; full long value and stale clipboard guard verified.");
            return 0;
        } finally { SetClipboardVerified(previous);app.Shutdown(); }
    }
}

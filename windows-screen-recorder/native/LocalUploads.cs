using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

// Deliberately limited to the isolated actual-renderer fixture. This does not
// authorize a live intake write or claim production upload integration.
static class LocalUploads {
    static readonly UIntPtr ConfirmTag=new UIntPtr(0x53435550);
    [StructLayout(LayoutKind.Sequential)] struct KeyInput {public ushort vk,scan;public uint flags,time;public UIntPtr extra;}
    [StructLayout(LayoutKind.Explicit,Size=40)] struct ConfirmInput {[FieldOffset(0)]public uint type;[FieldOffset(8)]public KeyInput key;}
    [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint count,ConfirmInput[] input,int size);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    public static bool OwnConfirmKey(uint flags,UIntPtr extra,uint vk){return (flags&16)!=0&&extra==ConfirmTag&&vk==13;}
    static void Confirm(AutomationElement field,IntPtr dialog,Action check) {
        check();field.SetFocus();check();
        if(Native.GetAncestor(Native.GetForegroundWindow(),2)!=dialog||!field.Current.HasKeyboardFocus||!Automation.Compare(field,AutomationElement.FocusedElement))throw new Exception("Filename confirmation focus changed.");
        foreach(int key in new[]{0x10,0x11,0x12,0x5B,0x5C,0x0D})if((GetAsyncKeyState(key)&0x8000)!=0)throw new Exception("Release held keys before filename confirmation.");
        var down=new ConfirmInput{type=1,key=new KeyInput{vk=13,extra=ConfirmTag}};
        var up=new ConfirmInput{type=1,key=new KeyInput{vk=13,flags=2,extra=ConfirmTag}};
        uint sent=SendInput(2,new[]{down,up},40);
        if(sent!=2){if(sent==1)SendInput(1,new[]{up},40);throw new Exception("Filename confirmation incomplete; selection was not repeated.");}
    }
    [ThreadStatic] static string stage;
    public const string Page="http://127.0.0.1:18962/?page=product_uploads";
    public static readonly string Input=Path.Combine(ChatSubmission.ReceiptDirectory,"local-upload-inputs.json");
    static readonly string[] Roles={"Man Cave","Office","Living Room"};
    static readonly string[] Slots={"01-man-cave-prompt","02-office-prompt","03-living-room-prompt"};
    static string Hash(string path){using(var s=File.OpenRead(path))using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(s)).Replace("-","").ToLowerInvariant();}
    public static void Validate(Dictionary<string,object> value) {
        var items=(IList)value["images"];if(items.Count!=3)throw new Exception("Exactly three role-bound originals required.");
        var roles=new HashSet<string>();var hashes=new HashSet<string>();var paths=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(Dictionary<string,object> row in items) {
            string role=(string)row["role"],path=(string)row["path"],hash=(string)row["sha256"];
            if(!Roles.Contains(role)||!roles.Add(role)||!Path.IsPathRooted(path)||!paths.Add(Path.GetFullPath(path))||!File.Exists(path)||
                !path.EndsWith(".png",StringComparison.OrdinalIgnoreCase)||new FileInfo(path).Length>50*1024*1024||!hashes.Add(hash)||Hash(path)!=hash)
                throw new Exception("An original is missing, changed or assigned ambiguously. No upload allowed.");
        }
    }
    static AutomationElement Unique(AutomationElement root,Condition condition) {
        var nodes=root.FindAll(TreeScope.Descendants,condition);if(nodes.Count!=1)throw new Exception("Upload control is missing or ambiguous at "+stage+" ("+nodes.Count+").");return nodes[0];
    }
    static Condition Named(string name){return new PropertyCondition(AutomationElement.NameProperty,name);}
    public static bool OwnedOpen(IntPtr h,IntPtr browser) {
        var kind=new System.Text.StringBuilder(256);Native.GetClassName(h,kind,256);
        return h!=browser&&Native.GetAncestor(h,3)==browser&&kind.ToString()=="#32770"&&Native.Title(h)=="Open";
    }
    public static bool Focus(IntPtr browser) {
        var h=Native.GetAncestor(Native.GetForegroundWindow(),2);
        return h==browser||OwnedOpen(h,browser);
    }
    public static bool Matches(IntPtr h) {
        if(!BrowserTabs.Chromium(h))return false;
        var root=AutomationElement.FromHandle(h);
        var docs=root.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Document));
        int count=0;foreach(AutomationElement doc in docs){object v=doc.GetCurrentPropertyValue(ValuePattern.ValueProperty,true);if(v is string&&(string)v==Page)count++;}
        return count==1&&root.FindAll(TreeScope.Descendants,Named("Sports Cave recorder upload test")).Count==1;
    }
    static string Receipt(IntPtr h) {
        if(!Matches(h))throw new Exception("The isolated upload page changed. No input allowed.");
        var texts=AutomationElement.FromHandle(h).FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text));
        var paths=new List<string>();foreach(AutomationElement t in texts)if(t.Current.Name.StartsWith("Local receipt: "))paths.Add(t.Current.Name.Substring(15));
        if(paths.Count!=1)throw new Exception("The current upload run is ambiguous.");
        string path=Path.GetFullPath(paths[0]);string root=Path.Combine(Path.GetTempPath(),"sc-pu-4b18037e","mockup-runs")+Path.DirectorySeparatorChar;
        if(!path.StartsWith(root,StringComparison.OrdinalIgnoreCase)||Path.GetFileName(path)!="recorder-upload-receipt.json"||!File.Exists(path))throw new Exception("Receipt is outside the isolated test run.");
        return path;
    }
    static Dictionary<string,object> Read(string path){return new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path));}
    static string StableReceipt(IntPtr window,Action check,Action heartbeat) {
        var wait=Stopwatch.StartNew();
        while(wait.ElapsedMilliseconds<10000) {
            check();heartbeat();
            try {if(Matches(window))return Receipt(window);}
            catch(ElementNotAvailableException) { /* A fragment replaced observed nodes. Re-observe only. */ }
            Thread.Sleep(100);
        }
        throw new Exception("The isolated upload identity did not settle. No further input allowed.");
    }
    public static string Run(IntPtr window,Dictionary<string,object> value,Action check,Action heartbeat) {
        Action cancellation=check;check=()=>{cancellation();if(!Focus(window))throw new Exception("Focus left the upload page or its owned picker.");};
        Validate(value);check();string receipt=StableReceipt(window,check,heartbeat);var before=Read(receipt);
        if(((Dictionary<string,object>)before["originals"]).Count!=0||Convert.ToInt32(((Dictionary<string,object>)before["readiness"])["ready_count"])!=5)
            throw new Exception("Reset only the isolated upload run before Play.");
        string intake=(string)before["intake"];
        for(int index=0;index<3;index++) {
            string role=Roles[index],slot=Slots[index];var row=((IList)value["images"]).Cast<Dictionary<string,object>>().Single(x=>(string)x["role"]==role);
            check();heartbeat();if(StableReceipt(window,check,heartbeat)!=receipt)throw new Exception("Upload run changed.");
            stage=role+" card";var region=Unique(AutomationElement.FromHandle(window),Named("Upload "+role+" image from ChatGPT"));
            stage=role+" upload button";
            var button=Unique(region,new AndCondition(Named("upload Upload"),new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button)));
            object invoke;if(!button.TryGetCurrentPattern(InvokePattern.Pattern,out invoke))throw new Exception("Upload control has no Invoke pattern.");
            ((InvokePattern)invoke).Invoke();
            IntPtr dialog=IntPtr.Zero;var timer=Stopwatch.StartNew();
            while(timer.ElapsedMilliseconds<8000&&dialog==IntPtr.Zero) {
                check();heartbeat();var matches=new List<IntPtr>();
                Native.EnumWindows((h,l)=>{if(Native.IsWindowVisible(h)&&OwnedOpen(h,window))matches.Add(h);return true;},IntPtr.Zero);
                if(matches.Count>1)throw new Exception("More than one owned Open dialog.");if(matches.Count==1)dialog=matches[0];else Thread.Sleep(100);
            }
            if(dialog==IntPtr.Zero)throw new Exception("The native Open dialog did not appear.");
            Native.CheckProcess(dialog);
            using(var owner=Native.ProcessFor(window))using(var modal=Native.ProcessFor(dialog))
                if(!String.Equals(owner.MainModule.FileName,modal.MainModule.FileName,StringComparison.OrdinalIgnoreCase))throw new Exception("Picker executable differs from browser.");
            if(!Native.SetForegroundWindow(dialog))throw new Exception("Could not activate the verified Open dialog.");
            var focusTimer=Stopwatch.StartNew();
            while(Native.GetAncestor(Native.GetForegroundWindow(),2)!=dialog&&focusTimer.ElapsedMilliseconds<1000){heartbeat();Thread.Sleep(25);}
            var dialogRoot=AutomationElement.FromHandle(dialog);
            stage="filename edit";var field=Unique(dialogRoot,new AndCondition(Named("File name:"),new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit)));
            stage="Open command";
            var open=Unique(dialogRoot,new AndCondition(new PropertyCondition(AutomationElement.AutomationIdProperty,"1"),new OrCondition(Named("Open"),Named("&Open"))));
            if(open.Current.Name.Replace("&","")!="Open")throw new Exception("Unexpected native Open label: "+open.Current.Name);
            object edit;if(!field.TryGetCurrentPattern(ValuePattern.Pattern,out edit)||!open.Current.IsEnabled)throw new Exception("Unsupported native Open controls.");
            check();if(Native.GetAncestor(Native.GetForegroundWindow(),2)!=dialog||Hash((string)row["path"])!=(string)row["sha256"])throw new Exception("Dialog focus or original bytes changed.");
            // Common-item dialogs can echo UIA SetValue without committing the
            // shell filename. Use the recorder's verified clipboard and tagged
            // paste, then verify the complete field before confirming once.
            ((ValuePattern)edit).SetValue("");
            var filenameTransfer=new RunTransfer();
            filenameTransfer.Copy(0,(string)row["path"],check);
            filenameTransfer.Get(0);
            ChatImageAttachment.Paste(field,check);
            var textTimer=Stopwatch.StartNew();
            while(((ValuePattern)edit).Current.Value!=(string)row["path"]&&textTimer.ElapsedMilliseconds<2000){check();heartbeat();Thread.Sleep(25);}
            if(((ValuePattern)edit).Current.Value!=(string)row["path"])throw new Exception("Native filename readback failed.");
            check();Confirm(field,dialog,check);
            timer.Restart();bool accepted=false;
            while(timer.ElapsedMilliseconds<30000) {
                check();heartbeat();if(Native.IsWindow(dialog)){Thread.Sleep(100);continue;}
                // Streamlit temporarily replaces the document during upload.
                // Observe only until the exact fixture identity returns; never
                // send the next input while its page identity is unavailable.
                if(StableReceipt(window,check,heartbeat)!=receipt)throw new Exception("Upload run changed after selection.");
                Dictionary<string,object> result;try{result=Read(receipt);}catch(IOException){Thread.Sleep(100);continue;}
                if(!Equals(result["intake"],intake))throw new Exception("Receipt intake changed.");
                var originals=(Dictionary<string,object>)result["originals"];
                if(originals.ContainsKey(slot+".txt")) {
                    var original=(Dictionary<string,object>)originals[slot+".txt"];
                    string expected=Path.Combine(Path.GetDirectoryName(receipt),"uploaded-originals",slot+".png");
                    if(!Equals(original["path"],expected)||!Equals(original["sha256"],row["sha256"])||Hash(expected)!=(string)row["sha256"])
                        throw new Exception("Accepted bytes do not match the selected role.");
                    if(Convert.ToInt32(((Dictionary<string,object>)result["readiness"])["ready_count"])==6+index){accepted=true;break;}
                }
                Thread.Sleep(100);
            }
            if(!accepted)throw new Exception("Upload acceptance was not verified; selection was not repeated.");
        }
        var final=Read(receipt);if(!Equals(((Dictionary<string,object>)final["readiness"])["complete"],true))throw new Exception("Eight-image readiness missing.");
        return receipt;
    }
}



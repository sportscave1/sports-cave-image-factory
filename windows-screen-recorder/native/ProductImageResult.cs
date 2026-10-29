using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Media;
using System.Windows.Media.Imaging;

// Image bytes and their digest remain in memory; neither enters the recording.
static class ProductImageResult {
    public const string Contract="sports-cave.product-image-copy.v1";
    public const string Ready="Copy black frame to clipboard", Success="Image copied";
    public static bool HasStatus(string help,string status) {
        if(help==null)return false;
        int matches=0;
        foreach(string line in help.Split('\n'))if(line==status)matches++;
        return matches==1;
    }
    [DllImport("user32.dll")] public static extern uint GetClipboardSequenceNumber();
    public static bool KnownButton(string app,string type,string id,string name) {
        return WindowIdentity.ChromiumApp(app)&&type=="Button"&&id=="copyImage"&&name=="Copy black frame";
    }
    public static bool Supports(Dictionary<string,object> target) {
        object scope,browser;
        return KnownButton((string)target["app"],(string)target["control_type"],(string)target["automation_id"],(string)target["name"])&&
            target.TryGetValue("scope",out scope)&&ProductCopyResult.HasFrameAnchors(scope as IList)&&
            target.TryGetValue("browser",out browser)&&((Dictionary<string,object>)browser).ContainsKey("product");
    }
    public static bool Fresh(uint before,uint observed,uint after,string acknowledgement) {
        return observed!=before&&observed==after&&HasStatus(acknowledgement,Success);
    }
    public static int PixelBytes(int width,int height) {
        long count=(long)width*height*4;
        if(width<1||height<1||width>16384||height>16384||count>128*1024*1024)
            throw new Exception("Clipboard image exceeds the bounded image transfer size.");
        return (int)count;
    }
    public static string Fingerprint() {
        return (string)Application.Current.Dispatcher.Invoke(new Func<string>(()=>{
            var image=Clipboard.GetImage();
            if(image==null)return null;
            var pixels=new byte[PixelBytes(image.PixelWidth,image.PixelHeight)];
            var normalized=new FormatConvertedBitmap(image,PixelFormats.Bgra32,null,0);
            normalized.CopyPixels(pixels,image.PixelWidth*4,0);
            using(var hash=SHA256.Create())return image.PixelWidth+"x"+image.PixelHeight+":"+Convert.ToBase64String(hash.ComputeHash(pixels));
        }));
    }
    public static bool Wait(uint before,Func<AutomationElement> observe,Action check,Action heartbeat,int timeoutMs,Action<uint,string> retain=null) {
        var timer=Stopwatch.StartNew();
        while(timer.ElapsedMilliseconds<timeoutMs) {
            check();heartbeat();
            var button=observe();
            if(button.Current.IsEnabled&&HasStatus(button.Current.HelpText,Success)) {
                uint observed=GetClipboardSequenceNumber();
                if(observed!=before) {
                    string first=Fingerprint();check();
                    if(first!=null&&Fresh(before,observed,GetClipboardSequenceNumber(),button.Current.HelpText)) {
                        string second=Fingerprint();check();
                        if(first==second&&observed==GetClipboardSequenceNumber()&&timer.ElapsedMilliseconds<timeoutMs) {
                            if(retain!=null)retain(observed,first);
                            return true;
                        }
                        throw new Exception("Clipboard image changed during copy verification.");
                    }
                }
            }
            Thread.Sleep(50);
        }
        return false;
    }
}

// A lease is issued only by the acknowledged Copy observer. It is never saved.
// Re-reading identical pixels cannot restore a lease after a clipboard change.
sealed class RunImageTransfer {
    readonly object gate=new object();
    uint sequence;string fingerprint;long generation;
    public void Clear(){lock(gate){sequence=0;fingerprint=null;generation++;}}
    public void Retain(uint observed,string image) {
        if(String.IsNullOrEmpty(image))throw new Exception("No verified clipboard image to retain.");
        lock(gate){sequence=observed;fingerprint=image;generation++;}
    }
    public bool Present {get{lock(gate)return fingerprint!=null;}}
    public string Verify(Func<uint> readSequence,Func<string> readImage) {
        uint expectedSequence;string expectedImage;long expectedGeneration;
        lock(gate){expectedSequence=sequence;expectedImage=fingerprint;expectedGeneration=generation;}
        if(expectedImage==null)throw new Exception("This run has no verified image Copy. Paste stopped.");
        // Never hold gate while invoking the UI dispatcher: Stop clears the lease
        // on that dispatcher and must not deadlock with a clipboard read.
        try {
            if(expectedSequence!=readSequence()||expectedImage!=readImage()||expectedSequence!=readSequence())
                throw new Exception("Clipboard changed after image Copy. Paste stopped.");
            lock(gate)if(generation!=expectedGeneration)throw new Exception("Image transfer was cleared during verification.");
            return expectedImage;
        } catch {Clear();throw;}
    }
    public string Verify(){return Verify(ProductImageResult.GetClipboardSequenceNumber,ProductImageResult.Fingerprint);}
}

static class ChatImageAttachment {
    public const string EditorName="New chat in SC Mockups/Uploads";
    public const string Page="https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project";
    public static readonly UIntPtr InputTag=new UIntPtr(0x53434950);
    // Low-level hooks report side-specific Ctrl even when SendInput uses VK_CONTROL.
    public static bool OwnPasteKey(uint flags,UIntPtr extra,uint vk) {
        return (flags&16)!=0&&extra==InputTag&&(vk==17||vk==162||vk==163||vk==86);
    }
    [StructLayout(LayoutKind.Sequential)] struct KeyInput {public ushort vk,scan;public uint flags,time;public UIntPtr extra;}
    [StructLayout(LayoutKind.Explicit,Size=40)] struct Input {[FieldOffset(0)]public uint type;[FieldOffset(8)]public KeyInput key;}
    [DllImport("user32.dll",SetLastError=true)] static extern uint SendInput(uint count,Input[] input,int size);
    [DllImport("user32.dll")] static extern short GetAsyncKeyState(int key);
    public static bool Supports(Dictionary<string,object> target) {
        object raw;
        if(!WindowIdentity.ChromiumApp((string)target["app"])||!Equals(target["control_type"],"Edit")||
           !Equals(target["name"],EditorName)||!target.TryGetValue("browser",out raw))return false;
        var browser=raw as Dictionary<string,object>;
        return browser!=null&&Equals(browser["page"],Page)&&Equals(browser["frame"],"top");
    }
    public static bool EmptyText(AutomationElement editor) {
        var identity=BrowserIdentity.Read(editor);
        return identity!=null&&Equals(identity["page"],Page)&&Equals(identity["frame"],"top")&&
            Equals(identity["control"],"label:textbox:"+EditorName)&&
            Array.IndexOf(editor.Current.HelpText.Split('\n'),"Sports Cave composer v1: empty")>=0;
    }
    public static AutomationElement Container(AutomationElement editor) {
        var parent=TreeWalker.ControlViewWalker.GetParent(editor);
        for(int depth=0;parent!=null&&depth<12;depth++,parent=TreeWalker.ControlViewWalker.GetParent(parent)) {
            if(parent.Current.ControlType==ControlType.Document||parent.Current.ControlType==ControlType.Window)break;
            var add=parent.FindAll(TreeScope.Descendants,new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
                new PropertyCondition(AutomationElement.NameProperty,"Add files and more")));
            if(add.Count!=1)continue;
            var edits=parent.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Edit));
            if(edits.Count!=1||!Automation.Compare(edits[0],editor))throw new Exception("Image paste composer is ambiguous.");
            return parent;
        }
        throw new Exception("The supported image composer could not be identified.");
    }
    public static bool Completed(string name,int images,int removals,int progress) {
        return images==1&&removals==1&&progress==0&&name!=null&&
            System.Text.RegularExpressions.Regex.IsMatch(name,@"^image\(\d{8}-\d{6}\)\.png$");
    }
    public static bool Inspect(AutomationElement editor,bool empty) {
        var container=Container(editor);int images=0,removals=0,progress=0;string name=null;
        var nodes=container.FindAll(TreeScope.Descendants,new OrCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Image),
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ProgressBar)));
        if(nodes.Count>50)throw new Exception("Image composer exceeded the observation bound.");
        foreach(AutomationElement node in nodes) {
            if(node.Current.ControlType==ControlType.ProgressBar)progress++;
            if(node.Current.ControlType==ControlType.Image&&!String.IsNullOrEmpty(node.Current.Name)){images++;name=node.Current.Name;}
            if(node.Current.ControlType==ControlType.Button&&node.Current.Name.StartsWith("Remove ",StringComparison.Ordinal))removals++;
        }
        if(empty)return images==0&&removals==0&&progress==0;
        if(!Completed(name,images,removals,progress))return false;
        return container.FindAll(TreeScope.Descendants,new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Button),
            new PropertyCondition(AutomationElement.NameProperty,"Remove "+name))).Count==1;
    }
    public static bool Wait(AutomationElement editor,RunImageTransfer image,Action check,Action heartbeat,int timeoutMs) {
        var timer=Stopwatch.StartNew();
        while(timer.ElapsedMilliseconds<timeoutMs) {
            check();heartbeat();image.Verify();
            if(!EmptyText(editor))throw new Exception("Image paste composer contains text or its empty-state marker is unavailable.");
            if(Inspect(editor,false)){check();return true;}
            Thread.Sleep(100);
        }
        return false;
    }
    static Input Key(ushort key,bool up){return new Input{type=1,key=new KeyInput{vk=key,flags=up?2u:0u,extra=InputTag}};}
    public static void Paste(AutomationElement editor,Action check) {
        check();
        foreach(int key in new[]{0x10,0x11,0x12,0x5B,0x5C,0x56})if((GetAsyncKeyState(key)&0x8000)!=0)
            throw new Exception("Release held keys before image Paste. No input sent.");
        editor.SetFocus();check();
        if(!editor.Current.HasKeyboardFocus||!Automation.Compare(editor,AutomationElement.FocusedElement))
            throw new Exception("Image paste focus changed. No input sent.");
        var batch=new[]{Key(0x11,false),Key(0x56,false),Key(0x56,true),Key(0x11,true)};
        uint sent=SendInput(4,batch,40);
        if(sent!=4) {
            // Release only keys this partial batch may have pressed; never retry Paste.
            if(sent>0)SendInput(2,new[]{Key(0x56,true),Key(0x11,true)},40);
            throw new Exception("Image paste input was incomplete. Inspect the draft; Paste was not repeated.");
        }
    }
}

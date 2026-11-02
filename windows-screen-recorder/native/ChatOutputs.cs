using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

static class ChatOutputs {
    public static AutomationElement One(AutomationElement root,ControlType type,string name,bool visible=true) {
        var nodes=root.FindAll(TreeScope.Descendants,new AndCondition(new PropertyCondition(AutomationElement.ControlTypeProperty,type),new PropertyCondition(AutomationElement.NameProperty,name)));
        AutomationElement found=null;foreach(AutomationElement node in nodes)if(!visible||!node.Current.IsOffscreen){if(found!=null)throw new Exception("Output control is ambiguous: "+name);found=node;}return found;
    }
    public static void Invoke(AutomationElement control,Action check) {
        object pattern;if(control==null||!control.Current.IsEnabled||!control.TryGetCurrentPattern(InvokePattern.Pattern,out pattern))throw new Exception("Output viewer control is unavailable.");
        check();((InvokePattern)pattern).Invoke();
    }
    public static bool Complete(bool generating,int images,int csv){return !generating&&images==3&&csv==1;}
    public static Dictionary<string,object> Wait(IntPtr window,Dictionary<string,object> value,Action check,Action heartbeat,int timeout) {
        string id=(string)value["request_id"],page=(string)value["conversation"];
        var ack=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(ChatSubmission.ReceiptDirectory,id+".json.ack")));
        if(!Equals(ack["request_id"],id)||!Equals(ack["conversation"],page)||!Equals(ack["acknowledged"],true))throw new Exception("Output wait requires the acknowledged request conversation.");
        Action verify=()=>{check();heartbeat();var current=BrowserIdentity.Current(window);
            if(current==null){var modal=One(AutomationElement.FromHandle(window),ControlType.Window,"Image preview");
                var anchor=modal==null?null:One(modal,ControlType.Button,"Generated image 2");
                if(anchor!=null)current=BrowserIdentity.Read(anchor);}
            if(current==null||!Equals(current["page"],page)||!Equals(current["profile"],ack["profile"]))throw new Exception("Output conversation changed.");};
        var timer=Stopwatch.StartNew();bool opened=false;
        while(timer.ElapsedMilliseconds<timeout) {
            verify();var root=AutomationElement.FromHandle(window);
            var preview=One(root,ControlType.Window,"Image preview");
            if(preview!=null&&!opened){Invoke(One(preview,ControlType.Button,"Close viewer"),verify);Thread.Sleep(150);continue;}
            if(preview==null&&!opened) {
                if(One(root,ControlType.Button,"Stop")!=null||One(root,ControlType.Button,"Stop streaming")!=null){Thread.Sleep(250);continue;}
                if(One(root,ControlType.Button,"Open preview of mockup-outputs.csv",false)==null){Thread.Sleep(250);continue;}
                var image=One(root,ControlType.Button,"Generated image 1");
                if(image==null){Thread.Sleep(250);continue;}
                Invoke(image,verify);opened=true;Thread.Sleep(150);continue;
            }
            if(preview==null){Thread.Sleep(150);continue;}
            int count=0;for(int n=1;n<=4;n++)if(One(preview,ControlType.Button,"Generated image "+n)!=null)count++;
            if(!Complete(false,count,1))throw new Exception("Generation finished but exactly three image outputs were not available. No new request was sent.");
            Invoke(One(preview,ControlType.Button,"Close viewer"),verify);
            var receipt=new Dictionary<string,object>{{"request_id",id},{"conversation",page},{"generation_complete",true},{"image_outputs",3},{"csv_name","mockup-outputs.csv"},{"download_bytes_verified",false}};
            string output=Path.Combine(ChatSubmission.ReceiptDirectory,id+".outputs.json");
            File.WriteAllText(output,new JavaScriptSerializer().Serialize(receipt));return receipt;
        }
        throw new Exception("Generation outputs are not all ready. Resume observation of this conversation; do not resubmit.");
    }
}

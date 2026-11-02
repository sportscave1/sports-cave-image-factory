using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
class ChatSubmissionChecks {
    static Type policy;static int checks;
    static object Call(string method,params object[] args){try{return policy.GetMethod(method).Invoke(null,args);}catch(TargetInvocationException e){throw e.InnerException;}}
    static void Require(bool value){checks++;if(!value)throw new Exception("Submission check "+checks+" failed");}
    static void Reject(Action action){bool failed=false;try{action();}catch{failed=true;}Require(failed);}
    static void Main(string[] args){
        policy=Assembly.LoadFrom(args[0]).GetType("ChatSubmission");
        string chat="https://chatgpt.com/c/12345678-1234-1234-1234-123456789abc";
        Require((bool)Call("Acknowledged","profile","profile",chat,1,true));
        Require((bool)Call("Conversation","https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/6ae2d62d-1338-83ec-8619-6ea3635a7fa0"));
        Require(!(bool)Call("Conversation","https://chatgpt.com/g/g-p-other-sc-mockups-uploads/c/6ae2d62d-1338-83ec-8619-6ea3635a7fa0"));
        Require(!(bool)Call("Acknowledged","other","profile",chat,1,true));
        Require(!(bool)Call("Acknowledged","profile","profile",chat,0,true));
        Require(!(bool)Call("Acknowledged","profile","profile",chat,2,true));
        Require(!(bool)Call("Acknowledged","profile","profile",chat,1,false));
        Require(!(bool)Call("Conversation","https://chatgpt.com/"));
        Require(!(bool)Call("Conversation",chat+"?secret=abc"));
        Require(!(bool)Call("Conversation",chat.Replace("chatgpt.com","evil.test")));
        Require(Equals(Call("Digest","complete\r\nprompt"),Call("Digest","complete\nprompt")));
        Require(!Equals(Call("Digest","complete\nprompt"),Call("Digest","complete\nprompt ")));
        string directory=Path.Combine(Path.GetTempPath(),"sc-submit-test-"+Guid.NewGuid().ToString("N"));
        var request=new Dictionary<string,object>{{"request_id",Guid.NewGuid().ToString("D")},{"sha256",new string('a',64)},{"characters",12}};
        int sends=0;string receipt=(string)Call("Begin",directory,request,"profile");sends++;
        Require(File.ReadAllText(receipt).Contains("attempted"));
        // Simulate lost acknowledgement and process restart: fresh call must not send.
        Reject(()=>{Call("Begin",directory,request,"profile");sends++;});Require(sends==1);
        File.WriteAllText(receipt+".ack","acknowledged");
        Reject(()=>{Call("Begin",directory,request,"profile");sends++;});Require(sends==1);
        File.Delete(receipt+".ack");
        var ack=new Dictionary<string,object>{{"request_id",request["request_id"]},{"conversation",chat},{"profile","profile"},{"acknowledged",true},{"generation_started",true}};
        Call("SaveAcknowledgement",receipt+".ack",ack);string saved=File.ReadAllText(receipt+".ack");
        Call("SaveAcknowledgement",receipt+".ack",ack);Require(File.ReadAllText(receipt+".ack")==saved);
        ack["conversation"]=chat.Replace("12345678","87654321");Reject(()=>Call("SaveAcknowledgement",receipt+".ack",ack));
        Require(File.ReadAllText(receipt+".ack")==saved);
        File.Delete(receipt+".ack");File.Delete(receipt);Directory.Delete(directory);
        policy=Assembly.LoadFrom(args[0]).GetType("ChatOutputs"); Require((bool)Call("Complete",false,3,1)); Require(!(bool)Call("Complete",true,3,1)); Require(!(bool)Call("Complete",false,2,1)); Require(!(bool)Call("Complete",false,4,1)); Require(!(bool)Call("Complete",false,3,0)); Console.WriteLine("PASS "+checks+" submission identity and durable ambiguous-send checks; no desktop input");
    }
}


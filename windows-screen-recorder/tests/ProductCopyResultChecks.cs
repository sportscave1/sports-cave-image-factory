using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;
class ProductCopyResultChecks {
    static Dictionary<string,object> Target(string path) {
        var task=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(path));
        return (Dictionary<string,object>)((Dictionary<string,object>)((ArrayList)task["actions"])[1])["target"];
    }
    static void Require(bool value,string message){if(!value)throw new Exception(message);}
    static List<ProductCopyResult.ScopeAnchor> Actual(ArrayList scope) {
        var result=new List<ProductCopyResult.ScopeAnchor>();
        foreach(Dictionary<string,object> entry in scope) {
            var current=entry;
            result.Add(new ProductCopyResult.ScopeAnchor((string)current["control_type"],(string)current["automation_id"],()=> (string)current["name"]));
        }
        return result;
    }
    static ProductCopyResult.ScopeAnchor Host(bool allowed=true) {
        return new ProductCopyResult.ScopeAnchor("Group","",()=>{throw new Exception("Excluded host name must never be read");},()=>allowed);
    }
    static void Main(string[] args) {
        string path=args[0];var target=Target(path);
        Require(ProductCopyResult.Supports(target),"actual captured Product Copy target is supported");
        ((Dictionary<string,object>)((ArrayList)target["scope"])[2])["automation_id"]="sc-product-upload-copy";
        Require(ProductCopyResult.Supports(target),"explicit application Copy frame is supported");
        var identified=(ArrayList)target["scope"];
        Require(ProductCopyResult.ScopeMatches(identified,Actual(identified)),"identified frame matches exactly");
        ((Dictionary<string,object>)identified[2])["automation_id"]="another-frame";
        Require(!ProductCopyResult.Supports(target),"unrecognized frame identity remains blocked");
        target=Target(path);
        target["name"]="Copied";Require(!ProductCopyResult.Supports(target),"transient labels cannot identify the command");
        target=Target(path);target["automation_id"]="copyImage";Require(!ProductCopyResult.Supports(target),"image copy requires its own result contract");
        target=Target(path);target["app"]=@"C:\Other\other.exe";Require(!ProductCopyResult.Supports(target),"other applications cannot inherit verification");
        target=Target(path);target.Remove("scope");Require(!ProductCopyResult.Supports(target),"unscoped invoke remains uncertain");
        target=Target(path);((Dictionary<string,object>)((ArrayList)target["scope"])[2])["name"]="other_component";
        Require(!ProductCopyResult.Supports(target),"same button ID in another iframe is excluded");
        target=Target(path);target["control_type"]="Edit";Require(!ProductCopyResult.Supports(target),"text fields cannot inherit verification");
        var expected=(ArrayList)Target(path)["scope"];var actual=Actual(expected);
        Require(ProductCopyResult.ScopeMatches(expected,actual),"original strict six-anchor scope remains valid");
        actual.Insert(3,Host());
        Require(ProductCopyResult.ScopeMatches(expected,actual),"observed anonymous host is accepted without reading its excluded label");
        actual=Actual(expected);actual.Insert(3,Host(false));
        Require(!ProductCopyResult.ScopeMatches(expected,actual),"protected or disabled hosts remain blocked");
        actual=Actual(expected);actual.Insert(3,Host());actual.Insert(4,new ProductCopyResult.ScopeAnchor("Group","",()=>"Second named host"));
        Require(!ProductCopyResult.ScopeMatches(expected,actual),"only one host group is optional");
        actual=Actual(expected);actual.Insert(3,new ProductCopyResult.ScopeAnchor("Group","modal",()=>"Modal"));
        Require(!ProductCopyResult.ScopeMatches(expected,actual),"identified groups cannot be skipped");
        actual=Actual(expected);actual.Insert(2,new ProductCopyResult.ScopeAnchor("Group","",()=>"Different context"));
        Require(!ProductCopyResult.ScopeMatches(expected,actual),"a group inside the iframe anchor boundary remains a mismatch");
        actual=Actual(expected);actual[2]=new ProductCopyResult.ScopeAnchor("Document","",()=>"Different component");
        Require(!ProductCopyResult.ScopeMatches(expected,actual),"iframe document identity remains exact");
        actual=Actual(expected);actual[4]=new ProductCopyResult.ScopeAnchor("Document","RootWebArea",()=>"Different page");
        Require(!ProductCopyResult.ScopeMatches(expected,actual),"outer page identity remains exact");
        var withHost=new ArrayList(expected);withHost.Insert(3,new Dictionary<string,object>{{"control_type","Group"},{"automation_id",""},{"name","[excluded]"}});
        Require(ProductCopyResult.ScopeMatches(withHost,Actual(expected)),"older saved host metadata can disappear without changing the recording");
        actual=Actual(expected);for(int i=0;i<17;i++)actual.Insert(0,new ProductCopyResult.ScopeAnchor("Pane","",()=>""));
        Require(!ProductCopyResult.ScopeMatches(expected,actual),"actual scope traversal is bounded");
        Console.WriteLine("PASS 20 Product Copy identity/privacy checks against actual saved target (no desktop input)");
    }
}

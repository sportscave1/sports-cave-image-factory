using System;
using System.Collections;
using System.Collections.Generic;
class ProductGenerationResultChecks {
    static int checks;
    static void Require(bool condition){checks++;if(!condition)throw new Exception("Generation result policy failed at "+checks);}
    static int Main() {
        string first=new string('a',32),second=new string('b',32);
        Func<string,string,string,ProductGenerationResult.Witness> read=(state,id,label)=>ProductGenerationResult.Parse(ProductGenerationResult.Container+"-"+state+"-"+id,label);
        var before=read("ready",first,"Mockups ready");
        Require(!ProductGenerationResult.Completed(before,read("ready",first,"Mockups ready")));
        Require(!ProductGenerationResult.Completed(before,read("working",second,"Generating mockups")));
        Require(ProductGenerationResult.Acknowledged(before,read("working",second,"Generating mockups")));
        Require(!ProductGenerationResult.Acknowledged(before,read("ready",first,"Mockups ready")));
        Require(!ProductGenerationResult.Acknowledged(before,read("failed",second,"Mockup generation failed")));
        Require(ProductGenerationResult.Completed(before,read("ready",second,"Mockups ready")));
        Require(!ProductGenerationResult.Completed(before,read("failed",second,"Mockup generation failed")));
        Require(!ProductGenerationResult.Completed(before,read("changed",second,"Product details changed")));
        Require(read("ready",second,"Generating mockups")==null);
        Require(read("ready","invalid","Mockups ready")==null);
        Require(!ProductGenerationResult.Completed(null,read("ready",second,"Mockups ready")));
        Require(!ProductGenerationResult.KnownButton("other.exe","Button","Generate mockups"));
        Require(ProductGenerationResult.KnownButton(@"C:\Apps\msedge.exe","Button","Generate mockups"));
        Func<string,string,string,object> anchor=(type,id,name)=>new Dictionary<string,object>{
            {"control_type",type},{"automation_id",id},{"name",name}};
        var scope=new ArrayList{anchor("Group","root",""),anchor("Document","RootWebArea","Product page"),anchor("Pane","","Product window")};
        Func<string,string,string,ProductCopyResult.ScopeAnchor> actual=(type,id,name)=>new ProductCopyResult.ScopeAnchor(type,id,()=>name,()=>true);
        var root=actual("Group","root","");var document=actual("Document","RootWebArea","Product page");var pane=actual("Pane","","Product window");
        var layout=new ProductCopyResult.ScopeAnchor("Group","",()=>{throw new Exception("Layout content name must not be read");},()=>true);
        Require(ProductGenerationResult.ScopeMatches(scope,new[]{root,document,pane}));
        Require(ProductGenerationResult.ScopeMatches(scope,new[]{layout,root,document,pane}));
        var main=actual("Group","stMain","");
        Require(ProductGenerationResult.ScopeMatches(scope,new[]{main,root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{main,main,root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{actual("Group","otherMain",""),root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{actual("Pane","stMain",""),root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{new ProductCopyResult.ScopeAnchor("Group","stMain",()=>"",()=>false),root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{layout,actual("Group","","Another named group"),root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{root,actual("Document","RootWebArea","Other page"),pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{root,document,actual("Pane","","Other window")}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{actual("Group","unexpected",""),root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{new ProductCopyResult.ScopeAnchor("Group","",()=>"",()=>false),root,document,pane}));
        Require(!ProductGenerationResult.ScopeMatches(scope,new[]{root,document}));
        Require(!ProductGenerationResult.ScopeMatches(new ArrayList{anchor("Group","root","")},new[]{root}));
        Console.WriteLine("PASS "+checks+" fresh generation acknowledgement policies; no UI/input used.");return 0;
    }
}

using System;
using System.Collections.Generic;
class ChromeCompatibilityChecks {
    static int checks;
    static void Require(bool value){checks++;if(!value)throw new Exception("Chrome policy check "+checks+" failed");}
    static int Main() {
        foreach(string app in new[]{@"C:\Apps\chrome.exe",@"C:\Apps\CHROME.EXE",@"C:\Apps\msedge.exe"}) {
            Require(WindowIdentity.ChromiumApp(app));
            Require(ProductGenerationResult.KnownButton(app,"Button","Generate mockups"));
            Require(ProductCopyResult.KnownButton(app,"Button","copyPrompt","Copy prompt"));
            Require(ProductPickerResult.KnownButton(app,"Button","choose","Choose PSD"));
            Require(ProductPickerResult.KnownScrollTarget(app,"picker","Choose PSD from Dropbox"));
            Require(!ProductGenerationResult.KnownButton(app,"Text","Generate mockups"));
            Require(!ProductCopyResult.KnownButton(app,"Button","wrong","Copy prompt"));
            Require(!ProductPickerResult.KnownButton(app,"Button","choose","Other picker"));
        }
        foreach(string app in new[]{"notepad.exe","chrome_proxy.exe","fakechrome.exe","chrome.exe.old","",null}) {
            Require(!WindowIdentity.ChromiumApp(app));
            Require(!ProductGenerationResult.KnownButton(app,"Button","Generate mockups"));
            Require(!ProductCopyResult.KnownButton(app,"Button","copyPrompt","Copy prompt"));
            Require(!ProductPickerResult.KnownButton(app,"Button","choose","Choose PSD"));
        }
        var a=new Dictionary<string,object>{{"profile","56578ebe-3793-47ba-b81f-fbc2c2755cf9"},{"page","https://sports-cave-image-factory.onrender.com/?page=product_uploads"},{"frame","top"},{"control","document"},{"product",new string('a',64)}};
        var b=new Dictionary<string,object>(a);
        Require(BrowserIdentity.SamePage(a,b));
        b["profile"]="11111111-1111-4111-8111-111111111111";Require(!BrowserIdentity.SamePage(a,b));
        b=new Dictionary<string,object>(a);b["page"]="https://chatgpt.com/";Require(!BrowserIdentity.SamePage(a,b));
        b=new Dictionary<string,object>(a);b["product"]=new string('b',64);Require(!BrowserIdentity.SamePage(a,b));
        // Chrome captions do not inherit Edge's relaxed tab-count title match.
        Require(!WindowIdentity.PlaybackTitleMatches("chrome.exe","SC - Profile - Microsoft Edge","SC and 1 more page - Profile - Microsoft Edge",p=>true));
        Console.WriteLine("PASS "+checks+" Chrome/Edge process and identity checks; no UI/input used.");return 0;
    }
}

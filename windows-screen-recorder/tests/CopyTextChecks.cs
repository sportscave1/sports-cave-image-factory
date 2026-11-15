using System;
static class Capture { internal static string Safe(string value) { return value; } }
class CopyTextChecks {
    static int count;
    static void Check(bool value) { if(!value)throw new Exception("Copy source assertion failed: "+count);count++; }
    static void Main() {
        Check(CopyText.Hash("abc")=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
        var hash=CopyText.Hash("Local source text");
        Check(CopyText.Matches("Local source text","source",hash));
        Check(!CopyText.Matches("Changed source text","source",hash));
        Check(!CopyText.Matches("Local source text","absent",hash));
        Check(!CopyText.Matches("Local source text","",hash));
        Check(!CopyText.Matches(new String('x',2001),"x",CopyText.Hash(new String('x',2001))));
        Check(CopyText.Matches("Café 🏆","🏆",CopyText.Hash("Café 🏆")));
        Console.WriteLine(count+" copy source checks passed; no clipboard or desktop access.");
    }
}

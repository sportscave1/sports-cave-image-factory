using System;
using System.Windows;
class PendingEditorClickChecks {
    static void Require(bool value,string reason){if(!value)throw new Exception(reason);}
    static void Main(){
        var click=new PendingEditorClick();var edge=new IntPtr(10);
        click.Begin(edge,100,200,3,1000);
        Require(click.CanResolve(edge,3,1200),"late focus in the original window can resolve");
        Require(!click.CanResolve(new IntPtr(11),3,1200),"another Edge window is rejected");
        Require(!click.CanResolve(edge,4,1200),"events across pause/resume are rejected");
        Require(!click.CanResolve(edge,3,3001),"expired clicks cannot authorize a text read");
        Require(!click.CanResolve(edge,3,999),"an observation cannot predate the click");
        bool rejected=false;try{click.Begin(edge,1,2,3,1100);}catch(InvalidOperationException){rejected=true;}
        Require(rejected,"a later click cannot silently overwrite an unresolved action");
        click.Clear();Require(!click.CanResolve(edge,3,1200),"a resolved click cannot be reused");
        var editor=new Rect(200,100,300,40);var label=new Rect(50,100,130,40);
        Require(EditorClickTarget.Matches(new Point(220,120),editor,Rect.Empty,false),"direct editor click is accepted");
        Require(EditorClickTarget.Matches(new Point(80,120),editor,label,true),"explicitly related label click is accepted");
        Require(!EditorClickTarget.Matches(new Point(80,120),editor,label,false),"an unvalidated label must not authorize a field read");
        Require(!EditorClickTarget.Matches(new Point(190,120),editor,label,true),"the gap between label and field is not expanded into a target");
        Require(!EditorClickTarget.Matches(new Point(0,0),Rect.Empty,Rect.Empty,true),"missing geometry cannot authorize a field read");
        Require(EditorClickTarget.Matches(new Point(-1200,150),new Rect(-1250,100,400,60),Rect.Empty,false),"physical coordinates on a negative-origin monitor are not rescaled");
        Console.WriteLine("PASS 13 delayed-editor and linked-label checks (no desktop input)");
    }
}

using System;
using System.Collections.Generic;
class ScrollTargetSearchChecks {
    class Node {public bool Inside=true,Scroll;public List<Node> Children=new List<Node>();}
    static ScrollTargetSearch<Node> Search(int nodes=256,int depth=16) {
        return new ScrollTargetSearch<Node>(n=>n.Inside,n=>n.Scroll,n=>n.Children,nodes,depth);
    }
    static void Require(bool value,string message){if(!value)throw new Exception(message);}
    static void Refused(Action action,string message){bool refused=false;try{action();}catch(InvalidOperationException){refused=true;}Require(refused,message);}
    static void Main() {
        var target=new Node{Scroll=true};var page=new Node();page.Children.Add(target);
        Require(Search().Find(page)==target,"unique inner scroll container resolves");
        Require(Search().Find(new Node())==null,"missing scroll position is not invented");
        page.Children.Add(new Node{Scroll=true});Refused(()=>Search().Find(page),"overlapping scroll containers are ambiguous");
        var outside=new Node{Inside=false,Scroll=true};outside.Children.Add(outside);
        page=new Node();page.Children.Add(outside);page.Children.Add(target);
        Require(Search().Find(page)==target,"outside branches are neither selected nor expanded");
        Refused(()=>Search(2).Find(page),"rejected nodes still count toward the inspection bound");
        page=new Node();var nested=new Node();nested.Children.Add(target);page.Children.Add(nested);
        Refused(()=>Search(256,1).Find(page),"depth is bounded even for unique candidates");
        page=new Node();page.Children.Add(page);Refused(()=>Search(5).Find(page),"provider cycles cannot create an unbounded search");
        Console.WriteLine("PASS 7 bounded scroll search checks (no desktop input)");
    }
}

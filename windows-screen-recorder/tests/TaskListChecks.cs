using System;
using System.Collections;
using System.Collections.Generic;
using System.Windows.Controls;
class TaskListChecks {
    static Dictionary<string,object> Row(string id,string name){return new Dictionary<string,object>{{"id",id},{"name",name},{"revision","immutable-"+id}};}
    static string Selected(ComboBox list){return (string)((Dictionary<string,object>)((ComboBoxItem)list.SelectedItem).Tag)["id"];}
    static void Require(bool value,string reason){if(!value)throw new Exception(reason);}
    [STAThread] static void Main(){
        var list=new ComboBox();var rows=new ArrayList(){Row("scroll","Scroll 21"),Row("controls","Controls 21")};
        TaskList.Update(list,rows,"scroll");list.SelectedIndex=1;var selected=list.SelectedItem;
        TaskList.Update(list,new ArrayList(){Row("scroll","Scroll 21"),Row("controls","Controls 21")},"scroll");
        Require(Selected(list)=="controls","an old run must not override the user's selection");
        Require(Object.ReferenceEquals(selected,list.SelectedItem),"unchanged snapshots must not rebuild an open dropdown");
        rows.Add(Row("new","New task"));TaskList.Update(list,rows,"scroll");
        Require(Selected(list)=="controls","catalog additions must preserve the selected task");
        rows.RemoveAt(1);TaskList.Update(list,rows,"scroll");
        Require(Selected(list)=="scroll","a removed task may fall back to the previous run");
        TaskList.Update(list,new ArrayList(),"scroll");Require(list.SelectedItem==null,"an empty catalogue clears selection");
        Console.WriteLine("PASS 5 actual WPF task-selection checks; no window or desktop input");
    }
}

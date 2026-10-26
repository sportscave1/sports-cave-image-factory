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
        var page=new ArrayList(){Row("old","Old selection")};var recent=Row("new","New saved or OS-played task");
        TaskList.Update(list,page,null,recent,"new");
        Require(Selected(list)=="new"&&list.Items.Count==2&&page.Count==1,"an off-page recent task is selected without changing its bounded page");
        list.SelectedIndex=0;TaskList.Update(list,page,null,recent);
        Require(Selected(list)=="old","an unchanged run must not override a later explicit selection");
        TaskList.Update(list,page,null,recent,"new");
        Require(Selected(list)=="new","a new completion must select its task even when rows are unchanged");
        TaskList.Update(list,new ArrayList(){recent},null,recent,"new");
        Require(list.Items.Count==1,"the selected task must not be duplicated on its own page");
        Console.WriteLine("PASS 9 actual WPF task-selection checks; no window or desktop input");
    }
}

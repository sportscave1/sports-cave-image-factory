using System;
using System.Collections;
using System.Collections.Generic;
using System.Windows.Controls;

static class TaskList {
    public static void Update(ComboBox list,ArrayList rows,string previousRun,Dictionary<string,object> recent=null,string prefer=null) {
        if(recent!=null) {
            bool present=false;
            foreach(Dictionary<string,object> row in rows)if(Object.Equals(row["id"],recent["id"]))present=true;
            if(!present){rows=new ArrayList(rows);rows.Add(recent);}
        }
        bool same=list.Items.Count==rows.Count;
        for(int i=0;same&&i<rows.Count;i++){
            var old=(Dictionary<string,object>)((ComboBoxItem)list.Items[i]).Tag;
            var row=(Dictionary<string,object>)rows[i];
            foreach(string key in new[]{"id","name","revision"})if(!Object.Equals(old[key],row[key]))same=false;
        }
        // Do not close/rebuild the dropdown while the user is choosing a task.
        if(same){
            // Metadata such as an on-demand preview can change without a
            // saved-definition revision. Keep selection and popup intact.
            for(int i=0;i<rows.Count;i++)((ComboBoxItem)list.Items[i]).Tag=rows[i];
            Prefer(list,prefer);
            return;
        }
        string selected=list.SelectedItem==null?null:(string)((Dictionary<string,object>)((ComboBoxItem)list.SelectedItem).Tag)["id"];
        list.Items.Clear();
        ComboBoxItem fallback=null;
        foreach(Dictionary<string,object> row in rows){
            var item=new ComboBoxItem(){Content=row["name"],Tag=row};list.Items.Add(item);
            if((string)row["id"]==selected)list.SelectedItem=item;
            if((string)row["id"]==previousRun)fallback=item;
        }
        if(list.SelectedItem==null&&fallback!=null)list.SelectedItem=fallback;
        if(list.Items.Count>0&&list.SelectedItem==null)list.SelectedIndex=0;
        Prefer(list,prefer);
    }
    static void Prefer(ComboBox list,string id) {
        if(id==null)return;
        foreach(ComboBoxItem item in list.Items)
            if(Object.Equals(((Dictionary<string,object>)item.Tag)["id"],id)){list.SelectedItem=item;return;}
    }
}

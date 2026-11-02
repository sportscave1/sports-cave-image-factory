using System;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Automation;
class TransferCaptureFixture {
    [STAThread] static void Main(string[] args) {
        var panel=new StackPanel{Margin=new Thickness(20)};
        panel.Children.Add(new TextBlock{Text="Disposable transfer recording — source"});
        var source=new TextBox{Text=File.ReadAllText(args[0]),AcceptsReturn=true,Height=100,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        AutomationProperties.SetAutomationId(source,"source");AutomationProperties.SetName(source,"Harmless source");panel.Children.Add(source);
        panel.Children.Add(new TextBlock{Text="Destination"});
        var destination=new TextBox{Text="",AcceptsReturn=true,Height=100,VerticalScrollBarVisibility=ScrollBarVisibility.Auto};
        AutomationProperties.SetAutomationId(destination,"destination");AutomationProperties.SetName(destination,"Harmless destination");panel.Children.Add(destination);
        new Application().Run(new Window{Title="Disposable transfer recording",Width=650,Height=330,Left=400,Top=220,Content=panel});
    }
}

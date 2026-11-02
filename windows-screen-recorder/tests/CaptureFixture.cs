using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Automation;
// Disposable local UI only. No network, files, automation, or production actions.
class CaptureFixture {
    [STAThread] static void Main(){
        var panel=new StackPanel{Margin=new Thickness(24)};
        panel.Children.Add(new TextBlock{Text="Disposable recorder test — prepared product 42",FontSize=18});
        panel.Children.Add(new TextBlock{Text="First value"});
        var first=new TextBox{Text="Prepared value",Margin=new Thickness(0,8,0,16)};
        AutomationProperties.SetAutomationId(first,"FirstValue");AutomationProperties.SetName(first,"First value");panel.Children.Add(first);
        panel.Children.Add(new TextBlock{Text="Second value"});
        var second=new TextBox{Text="Untouched",Margin=new Thickness(0,8,0,16)};
        AutomationProperties.SetAutomationId(second,"SecondValue");AutomationProperties.SetName(second,"Second value");panel.Children.Add(second);
        var check=new CheckBox{Content="Synthetic option",Margin=new Thickness(0,8,0,16)};
        AutomationProperties.SetAutomationId(check,"SyntheticOption");panel.Children.Add(check);
        new Application().Run(new Window{Title="Recorder disposable capture fixture",Width=560,Height=320,Left=400,Top=220,Content=panel});
    }
}

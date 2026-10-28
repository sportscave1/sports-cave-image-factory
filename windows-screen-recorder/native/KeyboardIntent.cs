static class KeyboardIntent {
    public static bool EditorTab(uint key,bool ctrl,bool alt) {return key==9&&!ctrl&&!alt;}
    public static bool BrowserTab(uint key,bool ctrl,bool alt) {return ctrl&&!alt&&(key==9||key==33||key==34);}
}

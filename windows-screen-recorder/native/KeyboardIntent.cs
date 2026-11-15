static class KeyboardIntent {
    public static bool ControlledPromptPaste(uint key,bool ctrl,bool alt,bool sameWindow,bool sameEpoch) {
        return key==86&&ctrl&&!alt&&sameWindow&&sameEpoch;
    }
    public static bool EditorTab(uint key,bool ctrl,bool alt) {return key==9&&!ctrl&&!alt;}
    public static bool BrowserTab(uint key,bool ctrl,bool alt) {return ctrl&&!alt&&(key==9||key==33||key==34);}
}

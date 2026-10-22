// Presentation only. Capture, action resolution and playback policies stay in
// their existing engine. Stop stays available during acknowledgements.
static class ToolbarPresentation {
    public static bool StopVisible(string state) {
        return state=="recording"||state=="paused"||state=="playing";
    }
    public static bool CanStart(string state,bool pending,bool connected) {
        return connected&&!pending&&state=="idle";
    }
    public static bool CanControl(string state,string action,bool pending,bool connected) {
        return connected&&(action=="Stop"?StopVisible(state):!pending);
    }
    public static string Label(string state,bool awaiting,bool playbackPaused,string pending,bool connected) {
        if(!connected)return "Disconnected";
        if(pending=="save")return "Saving…";
        if(pending=="stop")return "Stopping…";
        if(state=="playing")return awaiting?"Ready to play":playbackPaused?"Paused":"Playing";
        if(state=="recording")return "Recording";
        if(state=="paused")return "Paused";
        if(state=="draft")return "Ready to save";
        if(state=="interrupted")return "Recording interrupted";
        return pending=="record"?"Preparing…":"Idle";
    }
}

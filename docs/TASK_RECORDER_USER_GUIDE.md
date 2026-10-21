# Task Recorder: record and repeat actions

The Sports Cave OS page is your recording library. The Windows popup controls
recording and playback. The library/popup flow passed the physical controls trial;
use the matching Windows helper release when the updated page becomes available.

## Record

1. Open the Windows application and prepare the page/document you want to use.
2. In Sports Cave OS, open **Developer → Task Recorder → New recording**.
3. In the popup, select **Window to record**. If it is missing, use **Details →
   Refresh windows**. Choose the intended application's exact title.
4. Press **Record**, then perform the supported actions in that application.
5. Press **Stop** in the popup. The focused supported text field is flushed before
   the draft is offered for saving.
6. Keep the dated default name or edit it, then press **Save recording**. The saved
   recording appears in the OS library.

Use Pause/Resume in the popup to exclude temporary work from capture. If recording
interrupts, stop and read the reason. Review the preserved draft; do not assume
the unsupported action was captured. Discard only if you do not want that draft.

## Repeat

1. Open the same required application windows and restore the recording's starting
   context. For example, clear/reset a disposable text field or refresh a test page.
2. Click **Play** beside the saved recording in the OS library. This opens/restores
   the Windows popup with the selected revision ready; it has not run yet.
3. Click **Play** in the popup to let Windows focus the recorded applications.
4. Leave the mouse and keyboard alone. Check the final step count and actual
   application result when playback finishes.

Use **Pause/Resume** or **Stop** in the popup during playback. **Ctrl+Alt+F12** is
Emergency Stop. Manual input stops playback. If an action is uncertain or a
connection is lost, inspect the application before trying again; the recorder
does not automatically repeat an action whose effect is unknown.

## Manage and reconnect

- The row's **⋯** menu contains Rename, Edit and Delete. Windows action editing is
  currently read-only; make a new recording to change its actions. Rename preserves
  the action revision. Delete removes the Windows item from the library while
  retaining its definition for recovery.
- Advanced contains connection settings and the original browser-recording tools.
- If disconnected, open Task Recorder from the Windows Start menu, then refresh
  the OS connection. Pair only if this PC has not been connected before.
- Keep only one recorder popup open. If another popup prevents startup, close the
  idle older popup and choose New recording again.
- After an interrupted connection, an idle popup may still have a session review
  flag. Check the application's actual result, then use **Acknowledge Stop** on the
  OS page. This confirms the stopped session through the normal durable Stop
  receipt before enabling another Play; it does not repeat any actions.

## Supported actions

Supported semantic controls include text entry, checkbox/toggle, selection, menu
expansion, scroll and transitions to prepared, already-open windows. Availability
depends on the application's Windows accessibility provider. Protected/unknown
fields and ambiguous controls interrupt. This is not unrestricted mouse/keyboard
macro recording.

General button clicks remain uncertain without a supported result verifier.
Product Uploads Generate and Copy have specific verifiers from the completed
synthetic-provider trials; that does not imply arbitrary buttons or other apps are
verified. Newly opened windows, ambiguous taskbar previews and unsupported controls
may require a different workflow. Start with a harmless short recording.

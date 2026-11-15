"""Apply the isolated additive delta in memory for compatibility tests; no Git merge."""
import difflib
import re
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def compose(name,parent):
    old=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT).decode('utf-8').splitlines(keepends=True)
    new=(ROOT/name).read_text(encoding='utf-8').splitlines(keepends=True)
    for tag,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes():
        if tag=='equal':continue
        before=''.join(old[a:b]);after=''.join(new[c:d])
        if name.endswith('.cs') and '"capabilities", new[]' in before:
            parent=parent.replace('"openFile",','"openFile", "openWith", "appDefaults",',1);continue
        if name.endswith('.cs') and 'action != "openFile")' in before:
            parent=parent.replace('action != "openFile"','action != "openFile" && action != "openWith"',1);continue
        if before:
            prefix='' if parent.count(before)==1 else ''.join(old[max(0,a-2):a])
            context=prefix+before
            if parent.count(context)!=1:raise AssertionError('Ambiguous compatibility hunk: '+repr(context[:150]))
            parent=parent.replace(context,prefix+after,1)
        elif a==len(old):parent+=after
        else:
            anchor=old[a]
            prefix='' if parent.count(anchor)==1 else ''.join(old[max(0,a-2):a])
            context=prefix+anchor
            if parent.count(context)!=1:raise AssertionError('Ambiguous insertion anchor: '+repr(context))
            parent=parent.replace(context,prefix+after+anchor,1)
    return parent

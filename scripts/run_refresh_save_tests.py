"""Offline refresh regressions; provider transports are always blocked."""
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
os.environ['TEMP']=os.environ['TMP']=str(root/'tmp')
sys.path.insert(0,str(root))
import unittest
from unittest.mock import patch

if __name__=='__main__':
    with patch('requests.sessions.Session.request',side_effect=AssertionError('External requests forbidden in refresh tests')):
        unittest.main(module=None,argv=[sys.argv[0],*sys.argv[1:]])

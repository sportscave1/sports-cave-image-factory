import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from desktop_recorder.downloads import Download,DownloadError


class DownloadCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'report.txt').write_text('old content')

    def start(self,timeout=1):
        download=Download(self.root,'http://127.0.0.1:18963/disposable',timeout=timeout)
        download.created(download.nonce,'browser-download-42',download.source_url)
        return download

    def test_exact_duplicate_filename_receipt(self):
        download=self.start();path=self.root/'report (1).txt';body='New run\nUnicode 🦘'.encode();path.write_bytes(body)
        download.completed(download.nonce,'browser-download-42',path,len(body))
        self.assertEqual(download.wait(),(path,len(body),hashlib.sha256(body).hexdigest()))
        self.assertEqual((self.root/'report.txt').read_text(),'old content')

    def test_old_file_incomplete_and_wrong_receipt_rejected(self):
        download=self.start();path=self.root/'partial.crdownload';path.write_bytes(b'new')
        for nonce,ident,file,size in [(download.nonce,'browser-download-42',self.root/'report.txt',11),
            (download.nonce,'browser-download-42',path,3),('old-run','browser-download-42',path,3),
            (download.nonce,'different-download',path,3)]:
            with self.assertRaises(DownloadError):download.completed(nonce,ident,file,size)

    def test_cancel_and_timeout_never_fall_back(self):
        download=self.start();download.cancel()
        with self.assertRaises(DownloadError):download.wait()

    def test_renamed_old_file_is_not_a_new_download(self):
        download=self.start();path=self.root/'renamed.txt';(self.root/'report.txt').rename(path)
        with self.assertRaises(DownloadError):download.completed(download.nonce,'browser-download-42',path,11)
        download=self.start(timeout=.001)
        with self.assertRaises(DownloadError):download.wait()

    def test_save_as_supported_root_and_size_checked(self):
        download=self.start();directory=self.root/'Save As';directory.mkdir();path=directory/'chosen.txt';path.write_bytes(b'new')
        with self.assertRaises(DownloadError):download.completed(download.nonce,'browser-download-42',path,4)
        download.completed(download.nonce,'browser-download-42',path,3)
        self.assertEqual(download.wait()[0],path)

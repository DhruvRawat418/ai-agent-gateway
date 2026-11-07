import io
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
import update_duckdns as updater

class UpdateTests(unittest.TestCase):
    def opener(self, values):
        opener=Mock()
        opener.open.side_effect=[io.BytesIO(v.encode()) for v in values]
        return opener
    def test_imdsv2_and_explicit_ip(self):
        opener=self.opener(['metadata-token','13.59.164.76','OK'])
        self.assertEqual(updater.update({'domain':'dhruvaigateway','token':'secret'},opener),'13.59.164.76')
        calls=opener.open.call_args_list
        self.assertEqual(calls[0].args[0].method,'PUT')
        self.assertEqual(calls[1].args[0].get_header('X-aws-ec2-metadata-token'),'metadata-token')
        parsed=urlsplit(calls[2].args[0].full_url)
        self.assertEqual(parsed.scheme,'https')
        self.assertEqual(parse_qs(parsed.query)['ip'],['13.59.164.76'])
    def test_bad_metadata_never_updates_dns(self):
        opener=self.opener(['token','not-an-ip'])
        with self.assertRaises(ValueError):updater.update({'domain':'test','token':'secret'},opener)
        self.assertEqual(opener.open.call_count,2)
    def test_rejected_dns_update_fails(self):
        opener=self.opener(['token','13.59.164.76','KO'])
        with self.assertRaises(RuntimeError):updater.update({'domain':'test','token':'secret'},opener)
    def test_logs_never_include_token_url(self):
        with patch.object(updater.CONFIG.__class__,'read_text',return_value='{}'), patch.object(updater,'update',side_effect=URLError('https://example/?token=SECRET')), patch('sys.stderr',new_callable=io.StringIO) as stderr:
            self.assertEqual(updater.main(),1)
            self.assertNotIn('SECRET',stderr.getvalue())

if __name__=='__main__':unittest.main()

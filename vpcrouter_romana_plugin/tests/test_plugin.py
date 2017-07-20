"""
Copyright 2017 Pani Networks Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

#
# Unit tests for the Romana watcher plugin
#

import etcd3
import logging
import time
import unittest

from testfixtures                   import LogCapture

from vpcrouter.errors               import ArgsError
from vpcrouter.tests                import test_common

from vpcrouter_romana_plugin.romana import Romana


class TestPluginBase(unittest.TestCase):

    def setUp(self):
        self.lc = LogCapture()
        self.lc.setLevel(logging.DEBUG)
        self.lc.addFilter(test_common.MyLogCaptureFilter())
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.lc.uninstall()


class TestPluginConf(TestPluginBase):

    def test_conf(self):
        conf = {
            'addr' : "foobar"
        }
        # Fail because of missing port
        self.assertRaises(KeyError, Romana.check_arguments, conf)
        conf['port'] = 0
        # Fail because of invalid port
        self.assertRaises(ArgsError, Romana.check_arguments, conf)
        conf['port'] = 123
        # Fail because of invalid address
        self.assertRaises(ArgsError, Romana.check_arguments, conf)
        # Succeed with address specified
        conf['addr'] = "localhost"
        Romana.check_arguments(conf)
        conf['ca_cert'] = "foo-cert"
        self.assertRaisesRegexp(ArgsError, 'Either set all SSL auth options',
                                Romana.check_arguments, conf)
        conf['priv_key'] = "foo-key"
        self.assertRaisesRegexp(ArgsError, 'Either set all SSL auth options',
                                Romana.check_arguments, conf)
        conf['cert_chain'] = "cert-chain"
        self.assertRaisesRegexp(ArgsError, "Cannot access file 'foo-cert'",
                                Romana.check_arguments, conf)

    def test_run_no_connection(self):
        self.lc.clear()
        conf = {
            "port" : 59999,
            "addr" : "localhost"
        }
        plugin = Romana(conf, connect_check_time=0.5, etcd_timeout_time=0.5)
        plugin.start()
        time.sleep(1.5)
        self.lc.check(
            ('root', 'INFO',
             'Romana watcher plugin: Starting to watch for '
             'topology updates...'),
            ('root', 'DEBUG', 'Attempting to connect to etcd'),
            ('root', 'DEBUG', 'Initial data read'),
            ('root', 'ERROR',
             "Cannot load Romana topology data at '/romana/ipam/data': "),
            ('root', 'DEBUG',
             "Attempting to establish watch on '/romana/ipam/data'"),
            ('root', 'ERROR', 'Cannot establish connection to etcd: '),
            ('root', 'DEBUG', 'Cannot get status from etcd, no connection'),
            ('root', 'WARNING',
             'Romana watcher plugin: Lost etcd connection.'),
            ('root', 'DEBUG', 'Attempting to connect to etcd'),
            ('root', 'DEBUG', 'Initial data read'))

        plugin.stop()
        time.sleep(0.5)


class TestPluginMockEtcd(TestPluginBase):
    def setUp(self):
        super(TestPluginMockEtcd, self).setUp()
        self.orig_client = etcd3.client

    def cleanup(self):
        super(TestPluginMockEtcd, self).cleanup()
        etcd3.client = self.orig_client

    def test_run_mocked_connection(self):
        self.lc.clear()

        class MockClient(object):

            def add_watch_callback(self, key, func):
                pass

            def status(self):
                return True

            def get(self, key):
                return ("""
                    {
                        "AllocationRevision": 1,
                        "TopologyRevision": 4,
                        "address_name_to_ip": {
                            "x1": "10.0.0.0",
                            "x2": "10.0.0.4"
                        },
                        "networks": {
                            "net1": {
                                "blacked_out": [],
                                "block_mask": 30,
                                "cidr": "10.0.0.0/8",
                                "groups": {
                                    "block_to_host": {
                                        "0": "ip-192-168-99-10",
                                        "1": "ip-192-168-99-11"
                                    },
                                    "block_to_owner": {
                                        "0": "tenant1:",
                                        "1": "tenant1:"
                                    },
                                    "blocks": [
                                        {
                                            "cidr": "10.0.0.0/30",
                                            "pool": {
                                                "OrigMax": 167772163,
                                                "OrigMin": 167772160,
                                                "Ranges": [
                                                    {
                                                        "Max": 167772163,
                                                        "Min": 167772161
                                                    }
                                                ]
                                            },
                                            "revision": 1
                                        },
                                        {
                                            "cidr": "10.0.0.4/30",
                                            "pool": {
                                                "OrigMax": 167772167,
                                                "OrigMin": 167772164,
                                                "Ranges": [
                                                    {
                                                        "Max": 167772167,
                                                        "Min": 167772165
                                                    }
                                                ]
                                            },
                                            "revision": 1
                                        }
                                    ],
                                    "cidr": "10.0.0.0/8",
                                    "groups": null,
                                    "hosts": [
                                        {
                                            "agent_port": 0,
                                            "ip": "192.168.99.10",
                                            "name": "ip-192-168-99-10"
                                        },
                                        {
                                            "agent_port": 0,
                                            "ip": "192.168.99.11",
                                            "name": "ip-192-168-99-11"
                                        }
                                    ],
                                    "owner_to_block": {
                                        "tenant1:": [
                                            0,
                                            1
                                        ]
                                    },
                                    "reusable_blocks": [],
                                    "routing": "test"
                                },
                                "name": "net1",
                                "revision": 2
                            }
                        },
                        "tenant_to_network": {
                            "*": [
                                "net1"
                            ]
                        }
                    }
                    """, None)

        def mock_client_func(*args, **kwargs):
            return MockClient()

        etcd3.client = mock_client_func
        conf = {
            "port" : 59999,
            "addr" : "localhost"
        }
        plugin = Romana(conf, connect_check_time=0.5, etcd_timeout_time=0.5)
        plugin.start()
        time.sleep(0.5)
        plugin.stop()
        self.lc.check(
            ('root', 'INFO',
             'Romana watcher plugin: Starting to watch for '
             'topology updates...'),
            ('root', 'DEBUG', 'Attempting to connect to etcd'),
            ('root', 'DEBUG', 'Initial data read'),
            ('root', 'DEBUG',
             "Attempting to establish watch on '/romana/ipam/data'"),
            ('root', 'INFO',
             'Romana watcher plugin: Established etcd connection and '
             'watch for topology data'),
            ('root', 'DEBUG',
             'Sending stop signal to etcd watcher thread'),
            ('root', 'WARNING',
             'Romana watcher plugin: Lost etcd connection.'),
            ('root', 'INFO', 'Romana watcher plugin: Stopped'))

        q = plugin.get_route_spec_queue()
        d = q.get()
        self.assertEqual(d, {'10.0.0.0/8': ['192.168.99.10', '192.168.99.11']})
        time.sleep(0.5)

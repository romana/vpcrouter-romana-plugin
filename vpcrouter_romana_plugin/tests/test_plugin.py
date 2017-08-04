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
    """
    Base class for our tests, which sets up log capture.

    """
    def setUp(self):
        self.lc = LogCapture()
        self.lc.setLevel(logging.DEBUG)
        self.lc.addFilter(test_common.MyLogCaptureFilter())
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.lc.uninstall()


class TestPluginConf(TestPluginBase):
    """
    Testing config parsing and options.

    """
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
        # Fail because of missing address
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
        time.sleep(2.0)
        self.lc.check(
            ('root', 'INFO',
             'Romana watcher plugin: Starting to watch for '
             'topology updates...'),
            ('root', 'DEBUG', 'Attempting to connect to etcd (APIv3)'),
            ('root', 'DEBUG', 'Initial data read'),
            ('root', 'ERROR',
             "Cannot load Romana topology data at '/romana/ipam/data': "),
            ('root', 'DEBUG',
             "Attempting to establish watch on '/romana/ipam/data'"),
            ('root', 'ERROR', 'Cannot establish connection to etcd: '),
            ('root', 'DEBUG', 'Cannot get status from etcd, no connection'),
            ('root', 'WARNING',
             'Romana watcher plugin: Lost etcd connection.'),
            ('root', 'DEBUG', 'Attempting to connect to etcd (APIv3)'),
            ('root', 'DEBUG', 'Initial data read'))

        plugin.stop()
        time.sleep(0.5)


class TestPluginMockEtcd(TestPluginBase):
    """
    Testing different topology input configs.

    """
    def setUp(self):
        super(TestPluginMockEtcd, self).setUp()
        self.orig_client = etcd3.client

    def cleanup(self):
        super(TestPluginMockEtcd, self).cleanup()
        etcd3.client = self.orig_client

    def test_run_mocked_connection(self):
        self.lc.clear()

        # Mocking the etcd client

        class MockClient(object):

            def add_watch_callback(self, key, func):
                pass

            def status(self):
                return True

            def _set_mock_return_data(self, data):
                self.data = data

            def get(self, key):
                return (self.data, None)

        MOCK_CLIENT = MockClient()

        def mock_client_func(*args, **kwargs):
            return MOCK_CLIENT

        etcd3.client = mock_client_func

        conf = {
            "port" : 59999,
            "addr" : "localhost"
        }
        for test_input, expected_route_spec in [
                # Topology definition for simple, flat route spec
                ("""
                    {
                        "networks": {
                            "net1": {
                                "cidr": "10.0.0.0/8",
                                "host_groups": {
                                    "cidr": "10.0.0.0/8",
                                    "groups": null,
                                    "hosts": [
                                        { "ip": "192.168.99.10" },
                                        { "ip": "192.168.99.11" }
                                    ]
                                }
                            }
                        }
                    }
                 """,
                 {'10.0.0.0/8': ['192.168.99.10', '192.168.99.11']}),

                # Topology definition for simple, flat route spec, two nets
                ("""
                    {
                        "networks": {
                            "net1": {
                                "cidr": "10.0.0.0/8",
                                "host_groups": {
                                    "cidr": "10.0.0.0/8",
                                    "groups": null,
                                    "hosts": [
                                        { "ip": "192.168.99.10" },
                                        { "ip": "192.168.99.11" }
                                    ]
                                }
                            },
                            "net2": {
                                "cidr": "11.0.0.0/8",
                                "host_groups": {
                                    "cidr": "11.0.0.0/8",
                                    "groups": null,
                                    "hosts": [
                                        { "ip": "192.168.88.10" },
                                        { "ip": "192.168.88.11" }
                                    ]
                                }
                            }
                        }
                     }
                 """,
                 {'10.0.0.0/8': ['192.168.99.10', '192.168.99.11'],
                  '11.0.0.0/8': ['192.168.88.10', '192.168.88.11']}),

                # Topology definition without hosts (cannot make route spec)
                ("""
                   {
                       "networks": {
                           "net1": {
                               "cidr": "10.0.0.0/8",
                               "host_groups": {
                                   "cidr": "10.0.0.0/8",
                                   "groups": null,
                                   "hosts": [
                                   ]
                               }
                           }
                       }
                   }
                 """,
                 {}),

                # Topology definition without CIDR (cannot make route spec)
                ("""
                   {
                       "networks": {
                           "net1": {
                               "cidr": "10.0.0.0/8",
                               "host_groups": {
                                   "groups": null,
                                   "hosts": [
                                       { "ip": "192.168.99.10" },
                                       { "ip": "192.168.99.11" }
                                   ]
                               }
                           }
                       }
                   }
                 """,
                 {}),

                # Topology definition without groups (cannot make route spec)
                ("""
                   {
                       "networks": {
                           "net1": {
                               "cidr": "10.0.0.0/8",
                               "host_groups": {
                               }
                           }
                       }
                   }
                 """,
                 {}),

                # Several top-level groups
                ("""
                   {
                       "networks": {
                         "vlanA": {
                           "name": "vlanA",
                           "cidr": "10.1.0.0/16",
                           "host_groups": {
                             "routing": "",
                             "hosts": null,
                             "groups": [
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "1.1.1.1" },
                                   { "ip": "1.1.1.2" },
                                   { "ip": "1.1.1.3" }
                                 ],
                                 "groups": null,
                                 "cidr": "10.1.0.0/28"
                               },
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "2.2.2.2" }
                                 ],
                                 "groups": null,
                                 "cidr": "10.1.0.16/28"
                               },
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "3.3.3.3" }
                                 ],
                                 "groups": null,
                                 "cidr": "10.1.0.32/28"
                               },
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "4.4.4.4" }
                                 ],
                                 "groups": null,
                                 "cidr": "10.1.0.48/28"
                               }
                             ]
                           }
                         }
                      }
                   }
                 """,
                 {'10.1.0.32/28': ['3.3.3.3'],
                  '10.1.0.48/28': ['4.4.4.4'],
                  '10.1.0.0/28':  ['1.1.1.1', '1.1.1.2', '1.1.1.3'],
                  '10.1.0.16/28': ['2.2.2.2']}),

                # Deeper nesting of groups
                ("""
                   {
                       "networks": {
                         "vlanA": {
                           "name": "vlanA",
                           "cidr": "10.1.0.0/16",
                           "host_groups": {
                             "routing": "",
                             "hosts": null,
                             "groups": [
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "1.1.1.1" },
                                   { "ip": "1.1.1.2" },
                                   { "ip": "1.1.1.3" }
                                 ],
                                 "cidr": "10.1.0.0/28",
                                 "groups": [
                                    {
                                      "routing": "prefix-on-host",
                                      "hosts": [
                                        { "ip": "2.1.1.1" },
                                        { "ip": "2.1.1.2" },
                                        { "ip": "2.1.1.3" }
                                      ],
                                      "groups": null,
                                      "cidr": "10.1.0.4/29"
                                    }
                                 ]
                               },
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "2.2.2.2" }
                                 ],
                                 "groups": null,
                                 "cidr": "10.1.0.16/28"
                               },
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "3.3.3.3" }
                                 ],
                                 "groups": null,
                                 "cidr": "10.1.0.32/28"
                               },
                               {
                                 "routing": "prefix-on-host",
                                 "hosts": [
                                   { "ip": "4.4.4.4" }
                                 ],
                                 "groups": null,
                                 "cidr": "10.1.0.48/28"
                               }
                             ]
                           }
                         }
                      }
                   }
                 """,
                 {'10.1.0.32/28': ['3.3.3.3'],
                  '10.1.0.48/28': ['4.4.4.4'],
                  '10.1.0.0/28':  ['1.1.1.1', '1.1.1.2', '1.1.1.3'],
                  '10.1.0.4/29':  ['2.1.1.1', '2.1.1.2', '2.1.1.3'],
                  '10.1.0.16/28': ['2.2.2.2']})]:

            MOCK_CLIENT._set_mock_return_data(test_input)
            plugin = Romana(conf, connect_check_time=0.5,
                            etcd_timeout_time=0.5)
            plugin.start()
            time.sleep(0.5)
            plugin.stop()
            self.lc.check(
                ('root', 'INFO',
                 'Romana watcher plugin: Starting to watch for '
                 'topology updates...'),
                ('root', 'DEBUG', 'Attempting to connect to etcd (APIv3)'),
                ('root', 'DEBUG', 'Initial data read'),
                ('root', 'DEBUG',
                 "Sending route spec for routes: %s" %
                 [unicode(i) for i in expected_route_spec.keys()]),
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
            self.lc.clear()

            q = plugin.get_route_spec_queue()
            is_route_spec = q.get()
            self.assertEqual(is_route_spec, expected_route_spec)
            time.sleep(0.5)

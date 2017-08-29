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
# A VPC router watcher plugin, which observes the topology information
# maintained by Romana 2.0 in etcd.
#

import datetime
import etcd      # etcd APIv2 support
import etcd3     # etcd APIv3 support
import json
import logging
import threading
import time

from vpcrouter.errors  import ArgsError
from vpcrouter.watcher import common

from . import __version__


class Romana(common.WatcherPlugin):
    """
    Implements the WatcherPlugin interface for the 'romana' plugin.

    """
    def __init__(self, *args, **kwargs):
        self.key                  = "/romana/ipam/data"
        self.connect_check_time   = kwargs.pop('connect_check_time', 5)
        self.etcd_timeout_time    = kwargs.pop('etcd_timeout_time', 2)
        self.keep_running         = True
        self.etcd                 = None
        self.etcd_latest_raw      = None
        self.etcd_latest_raw_time = None
        self.etcd_connect_time    = None

        self.watch_id             = None   # used for etcd APIv3
        self.watch_thread_v2      = None   # used for etcd APIv2
        self.watch_broken         = False

        super(Romana, self).__init__(*args, **kwargs)

        if self.conf.get('usev2'):
            self.v2 = True
        else:
            self.v2 = False

    def get_plugin_name(self):
        return "vpcrouter_romana_plugin.romana"

    def get_info(self):
        """
        Return stats and information about the plugin.

        """
        return {
            self.get_plugin_name() : {
                "version" : self.get_version(),
                "params" : {
                    "etcd_addr"  : self.conf['etcd_addr'],
                    "etcd_port"  : self.conf['etcd_port'],
                    "ca_cert"    : self.conf['ca_cert'],
                    "priv_key"   : self.conf['priv_key'],
                    "cert_chain" : self.conf['cert_chain'],
                },
                "raw_topology" : {
                    "time" : self.etcd_latest_raw_time,
                    "data" : self.etcd_latest_raw
                },
                "stats" : {
                    "etcd_connect_time" : self.etcd_connect_time
                }
            }
        }

    def stop_watches(self):
        """
        Depending on which watches was configured (callback for v3 or thread
        for v2, issues necessary instructions to stop those.

        """
        if self.watch_id:
            logging.debug("Cancel watch for etcd APIv3 on '%s'" % self.key)
            self.etcd.cancel_watch(self.watch_id)
            self.watch_id = None
        if self.watch_thread_v2:
            logging.debug("Stop watch thread for etcd APIv2 on '%s'" %
                          self.key)
            # I'm not really stopping this thread, because that thread sits in
            # a block watch statement. TODO
            self.watch_thread_v2 = None

    def load_topology_send_route_spec(self):
        """
        Retrieve latest topology info from Romana topology store and send
        new spec.

        The topology information may contain recursive definitions of groups.
        Those need to be traversed and the host information for each group
        collected.

        * A group may either have another group (child group) or a list of
          hosts.
        * A group always has a CIDR.

        """
        def _parse_one_group(elem, route_spec):
            # Recursive helper function to descend into the nested group
            # definitions and append to the route-spec any more CIDRs and host
            # lists that we may find.
            # At any given level, we may have more groups, hosts or both. We
            # should have a CIDR as well, especially if we have hosts.
            groups = elem.get("groups")
            hosts  = elem.get("hosts")
            cidr   = elem.get("cidr")
            if groups and type(groups) is list:
                for group in groups:
                    # Call one level deeper for every group we find
                    route_spec = _parse_one_group(group, route_spec)
            if cidr and hosts and type(hosts) is list:
                # Use the hosts and cidr to add an entry to the route spec
                host_ips = [h['ip'] for h in hosts]
                route_spec[cidr] = host_ips
            return route_spec

        # Get the topology data from etcd and parse it
        try:
            if self.v2:
                data = self.etcd.get(self.key).value
            else:
                data = self.etcd.get(self.key)[0]
            d = json.loads(data)
            self.etcd_latest_raw      = d
            self.etcd_latest_raw_time = datetime.datetime.now().isoformat()

            route_spec = {}
            # We have separate topology data for different networks
            for net_name, net_data in d['networks'].items():
                # Top level element is always 'groups' (not a list), while
                # further down 'groups' will be a list of groups.
                groups = net_data.get('host_groups')
                if groups and type(groups) is dict:
                    route_spec = _parse_one_group(groups, route_spec)
            # Sanity checking on the assembled route spec
            common.parse_route_spec_config(route_spec)
            # Sending the new route spec out on our message queue
            logging.debug("Sending route spec for routes: %s" %
                          route_spec.keys())
            self.q_route_spec.put(route_spec)

        except Exception as e:
            logging.error("Cannot load Romana topology data at '%s': %s" %
                          (self.key, str(e)))

    def event_callback_v3(self, event):
        """
        Event handler function for watch on Romana IPAM data.

        This is called when we use the APIv3 client and whenever there is an
        update to that data detected.

        """
        logging.info("Romana watcher plugin: Detected topology change in "
                     "Romana topology data")
        self.load_topology_send_route_spec()

    def watch_loop_v2(self):
        """
        Establishes a watch for changes on the Romana IPAM data.

        This is called when we use the APIv2 client and runs in an extra
        thread.

        """
        try:
            # By the time we get here, an update may have happened. So, get the
            # latest index from the latest result and start our watch there,
            # setting the value so that the first watch immediately returns and
            # we can send a route spec update.
            res        = self.etcd.get(self.key)
            next_index = res.etcd_index   # First watch immediately finds this
        except Exception as e:
            # If the etcd isn't healthy, or our data isn't there, then we need
            # to end this thread and try again. We use the watch_broken flag to
            # indicate failure of this thread.
            logging.warning("Romana watcher plugin: Cannot start watch loop: "
                            "%s" % str(e))
            self.watch_broken = True
            return

        while True:
            try:
                watch_res = self.etcd.watch(self.key,
                                            timeout=0,
                                            index=next_index)
                if watch_res:
                    next_index = watch_res.etcd_index + 1
                self.load_topology_send_route_spec()

            except:
                # Something wrong? We'll attempt to re-establish the watch
                # after a little wait.
                time.sleep(2)

    def etcd_check_status(self):
        """
        Check the status of the etcd connection.

        Return False if there are any issues.

        """
        if self.etcd:
            try:
                if self.v2:
                    res = self.etcd.get("/")
                    if res is None:
                        raise Exception("empty status result from etcd")
                else:
                    self.etcd.status()
                return True
            except Exception as e:
                logging.debug("Cannot get status from etcd: %s" % str(e))

        else:
            logging.debug("Cannot get status from etcd, no connection")

        return False

    def establish_etcd_connection_and_watch(self):
        """
        Get connection to ectd and install a watch for Romana topology data.

        """
        self.stop_watches()    # just in case this is a re-establishment
        if not self.etcd or not self.etcd_check_status() or \
                    (self.watch_id is None and self.watch_thread_v2 is None):
            try:
                if self.v2:
                    logging.debug("Attempting to connect to etcd (APIv2)")
                    self.etcd = etcd.client.Client(
                                        host=self.conf['etcd_addr'],
                                        port=int(self.conf['etcd_port']),
                                        read_timeout=self.etcd_timeout_time)

                else:
                    logging.debug("Attempting to connect to etcd (APIv3)")
                    self.etcd = etcd3.client(
                                        host=self.conf['etcd_addr'],
                                        port=int(self.conf['etcd_port']),
                                        timeout=self.etcd_timeout_time,
                                        ca_cert=self.conf.get('ca_cert'),
                                        cert_key=self.conf.get('priv_key'),
                                        cert_cert=self.conf.get('cert_chain'))

                self.etcd_connect_time = datetime.datetime.now().isoformat()

                logging.debug("Initial data read")
                self.load_topology_send_route_spec()

                logging.debug("Attempting to establish watch on '%s'" %
                              self.key)
                if self.v2:
                    self.watch_thread_v2 = threading.Thread(
                                                target = self.watch_loop_v2,
                                                name   = "RomanaMonV2",
                                                kwargs = {})
                    self.watch_thread_v2.daemon = True
                    self.watch_thread_v2.start()
                    self.watch_id = None
                else:
                    self.watch_id = self.etcd.add_watch_callback(
                                            self.key, self.event_callback_v3)
                    self.watch_thread_v2 = None

                logging.info("Romana watcher plugin: Established etcd "
                             "connection and watch for topology data")
            except Exception as e:
                logging.error("Cannot establish connection to etcd: %s" %
                              str(e))
                self.etcd     = None
                self.watch_id = None

    def watch_etcd(self):
        """
        Start etcd connection, establish watch and do initial read of data.

        Regularly re-checks the status of the connection. In case of problems,
        re-establishes a new connection and watch.

        """
        while self.keep_running:
            self.etcd = None

            self.watch_broken = False
            self.establish_etcd_connection_and_watch()

            # Slowly loop as long as the connection status is fine.
            while self.etcd_check_status() and self.keep_running \
                                and not self.watch_broken:
                time.sleep(self.connect_check_time)

            logging.warning("Romana watcher plugin: Lost etcd connection.")
            time.sleep(self.connect_check_time)

    def start(self):
        """
        Start the configfile change monitoring thread.

        """
        logging.info("Romana watcher plugin: "
                     "Starting to watch for topology updates...")
        self.observer_thread = threading.Thread(target = self.watch_etcd,
                                                name   = "RomanaMon",
                                                kwargs = {})

        self.observer_thread.daemon = True
        self.observer_thread.start()

    def stop(self):
        """
        Stop the config change monitoring thread.

        """
        # self.stop_watches()
        logging.debug("Sending stop signal to etcd watcher thread")
        self.keep_running = False
        self.observer_thread.join()
        logging.info("Romana watcher plugin: Stopped")

    @classmethod
    def get_version(self):
        """
        Return the version of the plugin.

        Built-in plugins should return the string "built-in", while external
        plugins should overwrite this and return their own version string.

        """
        return __version__

    @classmethod
    def add_arguments(cls, parser, sys_arg_list=None):
        """
        Add arguments for the Romana mode to the argument parser.

        """
        parser.add_argument('--etcd_addr', dest="etcd_addr",
                            default="localhost",
                            help="etcd's address to connect to "
                                 "(only in Romana mode, default: localhost)")
        parser.add_argument('--etcd_port', dest="etcd_port",
                            default="2379", type=int,
                            help="etcd's port to connect to "
                                 "(only in Romana mode, default: 2379)")
        parser.add_argument('--etcd_use_v2', dest="usev2", action='store_true',
                            help="use etcd APIv2 (only in Romana mode)")
        parser.add_argument('--etcd_ca_cert', dest="ca_cert", default=None,
                            help="Filename of PEM encoded SSL CA certificate "
                                 "(do not set for plain http connection "
                                 "to etcd)")
        parser.add_argument('--etcd_priv_key', dest="priv_key", default=None,
                            help="Filename of PEM encoded private key file "
                                 "(do not set for plain http connection "
                                 "to etcd)")
        parser.add_argument('--etcd_cert_chain', dest="cert_chain",
                            default=None,
                            help="Filename of PEM encoded cert chain file "
                                 "(do not set for plain http connection "
                                 "to etcd)")
        return ["etcd_addr", "etcd_port", "usev2",
                "ca_cert", "priv_key", "cert_chain"]

    @classmethod
    def check_arguments(cls, conf):
        """
        Sanity check options needed for Romana mode.

        """
        if 'etcd_port' not in conf:
            raise ArgsError("The etcd port needs to be specified "
                            "(--etcd_port parameter)")
        if 'etcd_addr' not in conf:
            raise ArgsError("The etcd address needs to be specified "
                            "(--etcd_addr parameter)")
        if not 0 < conf['etcd_port'] < 65535:
            raise ArgsError("Invalid etcd port '%d' for Romana mode." %
                            conf['etcd_port'])
        cert_args = [conf.get('ca_cert'), conf.get('priv_key'),
                     conf.get('cert_chain')]
        if any(cert_args):
            if not all(cert_args):
                raise ArgsError("Either set all SSL auth options "
                                "(--etcd_ca_cert, --etcd_priv_key, "
                                "--etcd_cert_chain), or none of them.")
            else:
                # Check that the three specified files are accessible.
                for fname in cert_args:
                    try:
                        with open(fname) as f:
                            d = f.read()
                            if not d:
                                raise ArgsError("No contents in file '%s'" %
                                                fname)
                    except Exception as e:
                        raise ArgsError("Cannot access file '%s': %s" %
                                        (fname, str(e)))

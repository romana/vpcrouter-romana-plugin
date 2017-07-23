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

import etcd3
import json
import logging
import threading
import time

from vpcrouter         import utils
from vpcrouter.errors  import ArgsError
from vpcrouter.watcher import common


class Romana(common.WatcherPlugin):
    """
    Implements the WatcherPlugin interface for the 'romana' plugin.

    """
    def __init__(self, *args, **kwargs):
        self.key                = "/romana/ipam/data"
        self.connect_check_time = kwargs.pop('connect_check_time', 2)
        self.etcd_timeout_time  = kwargs.pop('etcd_timeout_time', 2)
        self.keep_running       = True
        self.watch_id           = None
        self.etcd               = None
        super(Romana, self).__init__(*args, **kwargs)

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
            d = json.loads(self.etcd.get(self.key)[0])
            route_spec = {}
            # We have separate topology data for different networks
            for net_name, net_data in d['networks'].items():
                # Top level element is always 'groups' (not a list), while
                # further down 'groups' will be a list of groups.
                groups = net_data.get('groups')
                if groups and type(groups) is dict:
                    route_spec = _parse_one_group(net_data['groups'],
                                                  route_spec)
            # Sanity checking on the assembled route spec
            common.parse_route_spec_config(route_spec)
            # Sending the new route spec out on our message queue
            self.q_route_spec.put(route_spec)

        except Exception as e:
            logging.error("Cannot load Romana topology data at '%s': %s" %
                          (self.key, str(e)))

    def event_callback(self, event):
        """
        Event handler function for watch on Romana IPAM data.

        This is called whenever there is an update to that data detected.

        """
        logging.info("Romana watcher plugin: Detected topology change in "
                     "Romana topology data")
        self.load_topology_send_route_spec()

    def etcd_check_status(self):
        """
        Check the status of the etcd connection.

        Return False if there are any issues.

        """
        if self.etcd:
            try:
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
        if not self.etcd or not self.etcd_check_status() or \
                                                self.watch_id is None:
            try:
                logging.debug("Attempting to connect to etcd")
                self.etcd = etcd3.client(host=self.conf['addr'],
                                         port=int(self.conf['port']),
                                         timeout=self.etcd_timeout_time,
                                         ca_cert=self.conf.get('ca_cert'),
                                         cert_key=self.conf.get('priv_key'),
                                         cert_cert=self.conf.get('cert_chain'))

                logging.debug("Initial data read")
                self.load_topology_send_route_spec()

                logging.debug("Attempting to establish watch on '%s'" %
                              self.key)
                self.watch_id = self.etcd.add_watch_callback(
                                        self.key, self.event_callback)

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
            self.etcd     = None
            self.watch_id = None

            self.establish_etcd_connection_and_watch()

            # Slowly loop as long as the connection status is fine.
            while self.etcd_check_status() and self.keep_running:
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
        if self.watch_id:
            self.etcd.cancel_watch(self.watch_id)
        logging.debug("Sending stop signal to etcd watcher thread")
        self.keep_running = False
        self.observer_thread.join()
        logging.info("Romana watcher plugin: Stopped")

    @classmethod
    def add_arguments(cls, parser):
        """
        Add arguments for the Romana mode to the argument parser.

        """
        parser.add_argument('-a', '--address', dest="addr",
                            default="localhost",
                            help="etcd's address to connect to "
                                 "(only in Romana mode, default: localhost)")
        parser.add_argument('-p', '--port', dest="port",
                            default="2379", type=int,
                            help="etcd's port to connect to "
                                 "(only in Romana mode, default: 2379)")
        parser.add_argument('--ca_cert', dest="ca_cert", default=None,
                            help="Filename of PEM encoded SSL CA certificate "
                                 "(do not set for plain http connection "
                                 "to etcd)")
        parser.add_argument('--priv_key', dest="priv_key", default=None,
                            help="Filename of PEM encoded private key file "
                                 "(do not set for plain http connection "
                                 "to etcd)")
        parser.add_argument('--cert_chain', dest="cert_chain", default=None,
                            help="Filename of PEM encoded cert chain file "
                                 "(do not set for plain http connection "
                                 "to etcd)")
        return ["addr", "port", "ca_cert", "priv_key", "cert_chain"]

    @classmethod
    def check_arguments(cls, conf):
        """
        Sanity check options needed for Romana mode.

        """
        if not 0 < conf['port'] < 65535:
            raise ArgsError("Invalid etcd port '%d' for Romana mode." %
                            conf['port'])
        if not conf['addr'] == "localhost":
            # Check if a proper address was specified
            utils.ip_check(conf['addr'])
        cert_args = [conf.get('ca_cert'), conf.get('priv_key'),
                     conf.get('cert_chain')]
        if any(cert_args):
            if not all(cert_args):
                raise ArgsError("Either set all SSL auth options (--ca_cert, "
                                "--priv_key, --cert_chain), or none of them.")
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
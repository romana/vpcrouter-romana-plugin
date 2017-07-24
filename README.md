# VPC-router Romana Plugin

The Romana 2.0 plugin for the
[vpc-router](https://github.com/romana/vpc-router) enables vpc-router
to fully integrate with [Romana 2.0](https://github.com/romana/romana): Routes
to subnets in different AWS availability zones are automatically managed, so
that Kubernetes clusters can be built across multiple availability zones, and
without the need for any overlay or tunneling network. Just beautifully simple,
natively routed networking.


## Deployment

### Running in a container

Pre-built containers for the vpc-router with Romana plugin are provided on
Quay.io. You can download the latest version:

    $ docker pull quay.io/romana/vpcrouter-romana-plugin

If you prefer to build your own container, a [Dockerfile](Dockerfile) has been
provided with the software. To build your own container, use:

    $ docker build -t yourname/vpcrouter-romana-plugin:1.1.0 .

Please note that this contains the vpc-router base installation in addition to
the vpc-router Romana plugin.

### Command line options

* `-m vpcrouter_romana_plugin.romana`: Select the Romana plugin.
* `-a <etcd-IP-address>`: Specify the IP address of the Romana etcd instance.
* `-p <etcd-port>`: Specify the port of the Romana etcd instance.
* `-l <logfile|->`: Specify the name of the logfile, or '-' to log to stdout.

The following options are only needed if the etcd instance is secured with SSL
certificates:

* `--ca_cert`: Filename of the PEM encoded SSL CA certificate.
* `--priv_key`: Filename of the PEM encoded private key file.
* `--cert_chain`: Filename of the PEM encoded cert chain file.

A few command line arguments are set by default if you run the provided
container, while others still need to be specified.
Specifically, the etcd address and port (`-a` and `-p` options) need to be
given, as well as the SSL certificates related options, if needed.

For example, run the container with these options:

    $ docker run -v /<host-path-to-certs>:/certs \
        quay.io/romana/vpcrouter-romana-plugin \
            -a <etcd-ip-address> -p <etcd-port>
            --ca_cert /certs/ca.crt \
            --priv_key /certs/client.key \
            --cert_chain /certs/client.crt

If the etcd instance is not secured with certificates then the last three
options and the `-v` option can be omitted:

    $ docker run quay.io/romana/vpcrouter-romana-plugin \
            -a <etcd-ip-address> -p <etcd-port>

Note that in the container, vpc-router logs to stdout, which tends to be the
preferred log destination in containerized environments.

An example of the command line options when running vpc-router directly,
outside of the container (and also logging to stdout):

    $ vpcrouter -m vpcrouter_romana_plugin.romana \
            -l - \
            -a <etcd-ip-address> -p <etcd-port>
            --ca_cert /certs/ca.crt \
            --priv_key /certs/client.key \
            --cert_chain /certs/client.crt


## Contributing, development and testing

### Feedback

We welcome any feedback, comment, bug reports or feature requests. Please use
the project's [issue tracker](https://github.com/romana/vpcrouter-romana-plugin/issues)
to submit those.

### Developing locally

If you wish to contribute code, please submit pull requests. To start
development on your own machine, please clone the repo. Then step into the repo
directory and install the requirements:

    $ pip install -r requirements/develop.txt

Among other things, this also installs
[vpc-router](https://github.com/romana/vpc-router).

If you are developing the plugin - and have not done a proper install, yet -
make sure that it can be found when vpc-router attempts to dynamically load it.
To do so, set the `PYTHONPATH` environment variable. Assuming you are standing
in the top-level directory of the Romana plugin repo, you can do this:

    $ export PYTHONPATH="`pwd`"

Note that this is not necessary once the Romana plugin is properly installed
(`python setup.py install`), since this will put the Romana plugin in the
search path for imports.

You can now run vpc-router with the Romana plugin:

    $ vpcrouter -m vpcrouter_romana_plugin.romana ...

### Testing

You can run the plugin's unit tests via the `run_tests.sh` script:

    $ ./run_tests.sh

This also produces coverage reports in HTML format.

To test adherence to some simple style guides, please run:

    $ ./style_test.h


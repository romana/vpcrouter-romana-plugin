# vpcrouter-romana-plugin

The Romana 2.0 plugin for the
[vpc-router](https://github.com/romana/vpc-router) enables vpc-router
to fully integrate with [Romana 2.0](https://github.com/romana/romana): Routes
to subnets in different availability zones are automatically managed, so that
Kubernetes clusters can be built across multiple availability zones, and
without the need for any overlay or tunneling network. Just beautifully simple,
natively routed networking.

## Development and testing

Clone the repo. Then step into the repo directory and install the requirements:

    $ pip install -r requirements/develop.txt

Among other things, this also installs
[vpc-router](https://github.com/romana/vpc-router).

If you are developing the plugin (have not done a proper install, yet), make
sure that it can be found when vpc-router attempts to dynamically load it. To
do so, set the `PYTHONPATH` environment variable. Assuming you are standing in
the top-level directory of the Romana plugin repo, you can do this:

    $ export PYTHONPATH="`pwd`"

Note that this is not necessary once the Romana plugin is properly installed
(`python setup.py install`), since this will put the Romana plugin in the
search path for imports.

You can now run vpc-router with the Romana plugin:

    $ vpcrouter -m vpcrouter_romana_plugin.romana ...

## Running in a container

Pre-built containers for the vpc-router with Romana plugin are provided on
Quay.io. You can download the latest version:

    $ docker pull quay.io/romana/vpcrouter-romana-plugin

If you prefer to build your own container, a [Dockerfile](Dockerfile) has been
provided with the software. To build your own container, use:

    $ docker build -t yourname/vpcrouter-romana-plugin:1.0.1 .

Please note that this contains the vpc-router base installation in addition to
the vpc-router Romana plugin.

A few command line arguments are set by default in the container, while
others still need to be specified when you run the container. Specifically,
the etcd address and port (`-a` and `-p` options) need to be given. If you
have an etcd installation secured via SSL certificates then you also need to
provide these three additional parameters, which allow etcd to authenticate
vpc-router as a client:

* `--ca_cert`: Filename of the PEM encoded SSL CA certificate.
* `--priv_key`: Filename of the PEM encoded private key file.
* `--cert_chain`: Filename of the PEM encoded cert chain file.

For example, to use the romana mode, run the container with these options:

    $ docker run quay.io/romana/vpcrouter-romana-plugin \
            -v /<host-path-to-certs>:/certs
            -a <etcd-ip-address> -p <etcd-port>
            --ca_cert /certs/ca.crt \
            --priv_key /certs/client.key \
            --cert_chain /certs/client.crt

If the etcd instance is not secured with certificates then the last three
options can be omitted.

Note that in the container, vpc-router logs to stdout, which tends to be the
preferred log destination in containerized environments.


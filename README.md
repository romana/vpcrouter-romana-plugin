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

Among other things, this also installs vpc-router.

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


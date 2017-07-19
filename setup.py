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

import os

from setuptools import setup, find_packages


import vpcrouter_romana_plugin


here = os.path.abspath(os.path.dirname(__file__))


def get_readme():
    try:
        import pypandoc
        return pypandoc.convert('README.md', 'rst')
    except (IOError, ImportError):
        return ""


long_description = get_readme()


setup(
    name                 = 'vpcrouter_romana_plugin',
    version              = vpcrouter_romana_plugin.__version__,
    url                  = "http://github.com/romana/vpcrouter-romana-plugin/",
    license              = "Apache Software License",
    author               = "Juergen Brendel",
    author_email         = "jbrendel@paninetworks.com",
    description          = "Romana 2.0 plugin for the vpc-router",
    long_description     = long_description,
    packages             = find_packages(),
    include_package_data = True,
    install_requires     = [
        'etcd3==0.6.2',
        'vpcrouter==1.3.1'
    ],
    dependency_links=[
        "http://github.com/romana/vpc-router/tarball/master#egg=vpcrouter-1.3.1"
    ],
    classifiers          = [
        'Programming Language :: Python',
        'Development Status :: 5 - Stable',
        'Natural Language :: English',
        'Environment :: Plugins',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Topic :: System :: Clustering',
        'Topic :: System :: Networking'
    ]
)

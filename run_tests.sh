#!/bin/bash

# Run all the unit tests and create a coverage report.

COVERAGE_REPORT_DIR=/tmp/vpcrouter-romana-plugin-coverage
nosetests -v --with-coverage --cover-erase \
          --cover-html --cover-html-dir=$COVERAGE_REPORT_DIR \
          --cover-package vpcrouter_romana_plugin

echo "@@@ Coverage report: file://$COVERAGE_REPORT_DIR/index.html"
echo

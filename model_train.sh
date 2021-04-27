#!/bin/bash -x

set -e

trap exit SIGINT

ulimit -v 16000000000

python strips.py reproduce-plot-dump-summary-planning lightsout digital 4 5000 None None None False ConcreteDetNormalizedLogitAddEffectTransitionAE "planning" 0.25